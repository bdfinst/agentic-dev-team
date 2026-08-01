#!/usr/bin/env python3
"""Round-level review-value instrumentation for `/code-review` (#1624).

`metrics/review-value.jsonl` today is written only by `/build`'s inline
checkpoints (#348) and records nothing about `/code-review`'s OWN fix-loop
rounds. That gap is why #1623's central question — is `correctness-review`'s
24-dispatch frequency delivering proportional value, or is it churn? — is
unanswerable, and why no churn-reduction mechanism can prove it worked.

This module writes one row per `/code-review` round to the same stream, with
`source: "code-review"` (the value `/harness-audit` Step 4 already knows to
exclude from fix-rate drop-candidate logic — see `knowledge/telemetry-schema.md`).

## The one judgment-free signal: fix provenance

`fix_provenance_new` counts how many of a round's NEW findings land inside
the line ranges the PREVIOUS round's fix actually touched. That is the
"the fix introduced it" signal, and it is computed by interval math over a
unified diff — no LLM judgment, no heuristics about finding text. A round
whose new error/warning findings ALL carry fix provenance is churn by
construction: every problem it found was created by the round before it.

Intervals are taken from the diff's **new side** (the `+` file's line
numbers), because that is the coordinate system findings are reported in:
an agent re-reading the post-fix file reports `file:line` against the
content that now exists on disk.

## Location & gating (issue #1624 design item 2)

Writes to `.claude/metrics/` **unconditionally**, matching
`boundary-events.jsonl` rather than `/build`'s consent-gated
`~/.claude/telemetry.json` path. Rationale, as recorded on the issue: this
is the same class of local, counts-only operational stream the commit gate
itself already depends on, and gating it behind consent would make the
epic's success criteria depend on consent being enabled on dev machines.
Rows carry counts, agent names, and enum values only — never code, file
content, or message text.

Stdlib-only. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# skills/code-review/scripts -> skills/code-review -> skills -> plugin root
_PLUGIN_ROOT = Path(__file__).resolve().parents[3]
_HOOKS_LIB_DIR = _PLUGIN_ROOT / "hooks" / "lib"
if str(_HOOKS_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_LIB_DIR))

try:
    import artifact_paths  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - degraded fallback, hooks/lib unreachable
    # Guarded-import form matching `change_shape.py`'s sibling pattern: this
    # directory is not in `ruff.toml`'s E402 per-file-ignore list, and the
    # import genuinely cannot precede the `sys.path` setup above. The fallback
    # resolves the same default location `artifact_paths.resolve_file` would,
    # minus the legacy-path migration — enough for an append-only metrics
    # writer that is already fail-open.
    artifact_paths = None

_STREAM_NAME = "review-value.jsonl"
_SOURCE = "code-review"

#: `dispatch_purpose` values. `discovery` = a panel looking for new problems
#: (round 1, and any full re-panel); `verification` = a re-dispatch confirming
#: a specific fix (#1628); `closing` = the scoped gate-closing pass (#1626).
DISPATCH_PURPOSES = ("discovery", "verification", "closing")

#: `outcome` values — the same closed enum `/build`'s rows already use, so the
#: two `source` values stay aggregatable in one query.
OUTCOMES = ("fixed", "no-op", "escalated")

#: `@@ -old,oldcount +new,newcount @@` — the counts are optional (git omits
#: `,1`), and anything may follow the closing `@@` (the hunk-header context).
_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def changed_line_intervals(diff_text: str) -> dict:
    """Parse a unified diff into `{path: [(start, end), ...]}` — inclusive
    NEW-side line ranges that the diff added or modified.

    Only `+` lines (and their positions) count as changed. A hunk that is
    pure deletion contributes no interval: there is no post-fix line for a
    finding to be reported against, so a deletion can never be the *site* of
    a new finding. Context lines advance the new-side counter without
    producing an interval.

    Paths come from the `+++ b/<path>` header with the `b/` prefix stripped;
    `/dev/null` (a pure delete) is skipped. Consecutive added lines collapse
    into one interval so the returned list stays small on large diffs.

    Malformed input degrades to fewer intervals, never to an exception — a
    caller that can't parse the diff simply gets no provenance credit, which
    is the conservative direction (it under-reports churn rather than
    inventing it).
    """
    intervals: dict = {}
    path: str | None = None
    new_line = 0
    run_start: int | None = None
    run_end: int | None = None

    def flush() -> None:
        nonlocal run_start, run_end
        if path is not None and run_start is not None and run_end is not None:
            intervals.setdefault(path, []).append((run_start, run_end))
        run_start = None
        run_end = None

    for raw in diff_text.splitlines():
        if raw.startswith("+++ "):
            flush()
            target = raw[4:].strip()
            # Strip git's `b/` prefix; tolerate `--src-prefix`-less diffs.
            if target == "/dev/null":
                path = None
            else:
                path = target.removeprefix("b/")
            new_line = 0
            continue
        if raw.startswith(("--- ", "diff --git ")):
            flush()
            continue
        match = _HUNK_RE.match(raw)
        if match:
            flush()
            new_line = int(match.group(1))
            continue
        if path is None:
            continue
        if raw.startswith("+"):
            if run_start is None:
                run_start = new_line
            run_end = new_line
            new_line += 1
        elif raw.startswith("-"):
            # Deletion: consumes an old-side line only. Does not advance the
            # new-side counter and never opens an interval.
            continue
        elif raw.startswith("\\"):
            # "\ No newline at end of file" — belongs to whichever side
            # preceded it and moves no counter.
            continue
        else:
            # Context line (leading space) or a stray blank line git emits
            # for an empty context line.
            flush()
            new_line += 1

    flush()
    return intervals


def _normalize_path(value: str) -> str:
    """Compare paths by their POSIX form without a leading `./`, so a finding
    reported as `./src/a.js` matches a diff header's `src/a.js`."""
    text = str(value).replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def finding_has_fix_provenance(finding: dict, intervals: dict) -> bool:
    """True when this finding's `file:line` falls inside a line range the
    previous round's fix touched — i.e. the fix is where this finding lives.

    A finding with no usable `line` (missing, non-integer, or <= 0) is NOT
    credited: "somewhere in a file the fix touched" is too weak a claim to
    call churn on. Same conservative direction as `changed_line_intervals`.
    """
    path = finding.get("file")
    if not isinstance(path, str) or not path:
        return False
    line = finding.get("line")
    if isinstance(line, bool) or not isinstance(line, int) or line <= 0:
        return False
    key = _normalize_path(path)
    for candidate, ranges in intervals.items():
        if _normalize_path(candidate) != key:
            continue
        if any(start <= line <= end for start, end in ranges):
            return True
    return False


def count_fix_provenance(findings, intervals: dict) -> int:
    """How many of `findings` land inside the previous round's fix delta."""
    return sum(1 for f in findings if isinstance(f, dict) and finding_has_fix_provenance(f, intervals))


def severity_breakdown(findings) -> dict:
    """`{errors, warnings, suggestions}` counts over a finding list — the
    same three-bucket shape `/build`'s rows already carry, so both `source`
    values aggregate in one query. Unrecognized severities are dropped
    rather than bucketed, keeping the three keys' sum meaningful."""
    counts = {"errors": 0, "warnings": 0, "suggestions": 0}
    bucket = {"error": "errors", "warning": "warnings", "suggestion": "suggestions"}
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        key = bucket.get(str(finding.get("severity", "")).lower())
        if key:
            counts[key] += 1
    return counts


def build_round_entry(
    *,
    round_number: int,
    agents_run,
    findings_new,
    findings_carried: int,
    dispatch_purpose: str,
    outcome: str,
    fix_diff: str = "",
    timestamp: str | None = None,
) -> dict:
    """Assemble one `review-value.jsonl` row for a `/code-review` round.

    `findings_new` is this round's NEW findings (carried-over signatures are
    counted separately via `findings_carried` — see #1625's round ledger,
    which owns signature identity). `fix_diff` is the unified diff of the
    PREVIOUS round's fix; empty for round 1, which by definition has no
    preceding fix and therefore always reports `fix_provenance_new: 0`.
    """
    if dispatch_purpose not in DISPATCH_PURPOSES:
        raise ValueError(f"dispatch_purpose must be one of {DISPATCH_PURPOSES}")
    if outcome not in OUTCOMES:
        raise ValueError(f"outcome must be one of {OUTCOMES}")

    findings = [f for f in findings_new if isinstance(f, dict)]
    intervals = changed_line_intervals(fix_diff) if fix_diff else {}
    return {
        "timestamp": timestamp or _now_iso(),
        "source": _SOURCE,
        "round": int(round_number),
        "agents_run": sorted({str(a) for a in agents_run}),
        "findings_new": len(findings),
        "findings_carried": int(findings_carried),
        "severity_breakdown": severity_breakdown(findings),
        "fix_provenance_new": count_fix_provenance(findings, intervals),
        "dispatch_purpose": dispatch_purpose,
        "outcome": outcome,
    }


def append_round(entry: dict, cwd=None) -> Path | None:
    """Append one row to `.claude/metrics/review-value.jsonl`.

    Fail-open on the write, matching every other metrics emitter in this
    plugin: a full disk or read-only metrics directory must never fail a
    review. Returns the path written, or `None` when the write failed.
    """
    try:
        base = Path(cwd) if cwd else Path.cwd()
        log = (
            artifact_paths.resolve_file("metrics", _STREAM_NAME, base)
            if artifact_paths is not None
            else base / ".claude" / "metrics" / _STREAM_NAME
        )
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, separators=(",", ":"), sort_keys=True) + "\n")
        return log
    except Exception:  # noqa: BLE001 - fail-open: telemetry never blocks a review
        return None


def _load_findings(path: str | None):
    if not path:
        return []
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    if not text.strip():
        return []
    data = json.loads(text)
    if isinstance(data, dict):
        data = data.get("findings", [])
    return data if isinstance(data, list) else []


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Append one /code-review round to review-value.jsonl")
    parser.add_argument("--round", type=int, required=True, dest="round_number")
    parser.add_argument(
        "--agents", default="", help="Comma-separated agent names dispatched this round"
    )
    parser.add_argument(
        "--findings",
        default=None,
        help="Path to this round's NEW findings JSON (a list, or {findings: [...]}); '-' for stdin",
    )
    parser.add_argument("--carried", type=int, default=0, dest="findings_carried")
    parser.add_argument("--purpose", required=True, choices=list(DISPATCH_PURPOSES))
    parser.add_argument("--outcome", required=True, choices=list(OUTCOMES))
    parser.add_argument(
        "--fix-diff",
        default=None,
        dest="fix_diff",
        help="Path to the PREVIOUS round's fix diff (unified); '-' for stdin. Omit for round 1.",
    )
    parser.add_argument("--cwd", default=None)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the row that would be appended without writing it",
    )
    args = parser.parse_args(argv)

    findings = _load_findings(args.findings)
    fix_diff = ""
    if args.fix_diff:
        fix_diff = (
            sys.stdin.read()
            if args.fix_diff == "-"
            else Path(args.fix_diff).read_text(encoding="utf-8")
        )

    entry = build_round_entry(
        round_number=args.round_number,
        agents_run=[a.strip() for a in args.agents.split(",") if a.strip()],
        findings_new=findings,
        findings_carried=args.findings_carried,
        dispatch_purpose=args.purpose,
        outcome=args.outcome,
        fix_diff=fix_diff,
    )
    if not args.dry_run:
        append_round(entry, args.cwd)
    print(json.dumps(entry, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
