#!/usr/bin/env python3
"""Validity check for the `review-value.jsonl` sample (#2019).

`review-value.jsonl` is the evidence base for every per-lens pruning or
tier-down decision (#1980, #1982, #1983, #2007). Both of its writers are
triggered by agent instruction rather than by mechanism — `/code-review`
rounds call `review_round_log.py` from a bash block in `SKILL.md`, and
`/build` checkpoints append the row by prose alone — so rows are collected
only when an agent remembers to collect them.

That failure is not uniform, and its direction is the problem. An agent that
found nothing is markedly less likely to run a "record the review value" step
than one that found something, so the rows that survive over-represent
productive rounds. #1512 measured exactly this and named it:

    ~100% "found something" on nearly every lens - because the only slices
    that got logged happened to have findings. This is a sampling artifact,
    not evidence a lens is valuable. Do not auto-prune yet.

Ten biased records were nearly used to prune lenses. This module exists so
that cannot happen silently again: it reconciles the value rows against the
dispatch ledger, which IS written deterministically by a hook, and reports
whether the sample can support a pruning decision at all.

## Why the ledger is a usable denominator

`agent_dispatch_ledger.py` writes one `boundary-events.jsonl` row per review
dispatch, carrying the agent name in `matched_rule`. It is a PostToolUse hook,
so it fires whether or not the round found anything - the exact property the
value stream lacks. Comparing the two gives a per-lens collection rate that no
amount of missing value rows can inflate.

The denominator is honest about its own limits: a dispatch the ledger missed
(hook disabled, older plugin version) is invisible here too, so coverage is an
upper bound on collection, never an under-estimate of the gap.

Stdlib-only. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

# skills/code-review/scripts -> skills/code-review -> skills -> plugin root
_PLUGIN_ROOT = Path(__file__).resolve().parents[3]
_HOOKS_LIB_DIR = _PLUGIN_ROOT / "hooks" / "lib"
if str(_HOOKS_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_LIB_DIR))

try:
    import artifact_paths  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - degraded fallback, hooks/lib unreachable
    # Same guarded-import shape as `review_round_log.py`: this directory is not
    # in `ruff.toml`'s E402 per-file-ignore list and the import cannot precede
    # the `sys.path` setup above.
    artifact_paths = None

VALUE_STREAM = "review-value.jsonl"
LEDGER_STREAM = "boundary-events.jsonl"

#: The ledger rows that denote a review dispatch.
_LEDGER_HOOK = "agent_dispatch_ledger"
_LEDGER_DECISION = "record"

#: Minimum rows before per-lens rates mean anything. #1512 set this figure
#: explicitly ("revisit at N >= ~100 records") after finding 10 records
#: unusable; it is carried here rather than re-derived so the threshold has
#: one home.
MIN_ROWS = 100

#: Minimum share of dispatches that must carry a value row. Below this the
#: logged rows are a subset selected by something other than chance, and
#: per-lens rates computed from them describe the selection, not the lens.
MIN_COVERAGE = 0.5

#: Minimum share of outcomes that must be `no-op`. A panel that never reports
#: a no-op across a large sample has not achieved perfection - it has failed
#: to log its quiet rounds, which is #1512's artifact exactly. The no-op rate
#: is also the precise quantity a pruning decision needs, so a sample without
#: it cannot answer the question being asked of it.
MIN_NOOP_SHARE = 0.05

#: `skipped` marks a review that did not run (e.g. a backstop suppressed by
#: `--backstop-review=skip`). It is neither a finding nor a quiet round, so it
#: is excluded from the no-op denominator rather than diluting it.
_NON_RUN_OUTCOMES = frozenset({"skipped"})

VERDICTS = (
    "no-data",
    "unverifiable",
    "undercollected",
    "insufficient",
    "biased",
    "usable",
)


def _resolve(stream: str, cwd: Path) -> Path:
    if artifact_paths is not None:
        return artifact_paths.resolve_file("metrics", stream, cwd)
    return cwd / ".claude" / "metrics" / stream


def read_jsonl(path: Path) -> tuple[list[dict], int]:
    """Return (rows, malformed_count).

    Malformed lines are skipped but **counted**. Silently dropping unreadable
    telemetry is the same class of defect this module exists to surface, so the
    count is reported rather than swallowed.
    """
    rows: list[dict] = []
    malformed = 0
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return rows, malformed
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except ValueError:
            malformed += 1
            continue
        if isinstance(parsed, dict):
            rows.append(parsed)
        else:
            malformed += 1
    return rows, malformed


def dispatch_counts(ledger_rows) -> Counter:
    """Per-agent dispatch counts from the deterministic ledger."""
    counts: Counter = Counter()
    for row in ledger_rows:
        if row.get("hook") != _LEDGER_HOOK:
            continue
        if row.get("decision") != _LEDGER_DECISION:
            continue
        agent = row.get("matched_rule")
        if isinstance(agent, str) and agent.strip():
            counts[agent.strip()] += 1
    return counts


def logged_counts(value_rows) -> Counter:
    """Per-agent appearances across value rows' `agents_run` lists."""
    counts: Counter = Counter()
    for row in value_rows:
        agents = row.get("agents_run")
        if not isinstance(agents, list):
            continue
        for agent in agents:
            if isinstance(agent, str) and agent.strip():
                counts[agent.strip()] += 1
    return counts


def noop_share(value_rows) -> float | None:
    """Share of *run* rounds whose outcome was `no-op`, or None if none ran."""
    outcomes = [
        row.get("outcome")
        for row in value_rows
        if isinstance(row.get("outcome"), str)
    ]
    ran = [o for o in outcomes if o not in _NON_RUN_OUTCOMES]
    if not ran:
        return None
    return sum(1 for o in ran if o == "no-op") / len(ran)


def assess(value_rows, ledger_rows) -> dict:
    """Reconcile the two streams and rule on whether the sample is usable."""
    dispatches = dispatch_counts(ledger_rows)
    logged = logged_counts(value_rows)
    total_dispatches = sum(dispatches.values())
    total_logged = sum(logged.values())

    coverage = (total_logged / total_dispatches) if total_dispatches else None
    share = noop_share(value_rows)
    reasons: list[str] = []

    if not value_rows:
        reasons.append(
            f"no value rows: {total_dispatches} dispatches recorded, 0 logged"
        )
    else:
        if coverage is None:
            # No denominator, so under-collection cannot be ruled out. Passing
            # here would make this check incapable of failing on exactly the
            # sample shape it exists to catch — #1512's rows were collected
            # before the ledger hook existed, and would certify clean.
            reasons.append(
                "no dispatch records: collection completeness cannot be "
                "verified without the agent_dispatch_ledger stream"
            )
        elif coverage < MIN_COVERAGE:
            reasons.append(
                f"coverage {coverage:.0%} below {MIN_COVERAGE:.0%} floor "
                f"({total_logged}/{total_dispatches} dispatches logged)"
            )
        if len(value_rows) < MIN_ROWS:
            reasons.append(
                f"{len(value_rows)} rows below the {MIN_ROWS}-row floor (#1512)"
            )
        if share is not None and share < MIN_NOOP_SHARE:
            reasons.append(
                f"no-op share {share:.0%} below {MIN_NOOP_SHARE:.0%} floor - "
                "quiet rounds are not reaching the log"
            )

    # Most severe first: a stream with nothing in it cannot be merely thin, and
    # an under-collected one cannot be trusted however many rows it holds.
    if not value_rows:
        verdict = "no-data"
    elif coverage is None:
        verdict = "unverifiable"
    elif coverage < MIN_COVERAGE:
        verdict = "undercollected"
    elif len(value_rows) < MIN_ROWS:
        verdict = "insufficient"
    elif share is not None and share < MIN_NOOP_SHARE:
        verdict = "biased"
    else:
        verdict = "usable"

    per_lens = {
        agent: {
            "dispatches": dispatches.get(agent, 0),
            "logged": logged.get(agent, 0),
            "coverage": (
                logged.get(agent, 0) / dispatches[agent] if dispatches.get(agent) else None
            ),
        }
        for agent in sorted(set(dispatches) | set(logged))
    }

    return {
        "verdict": verdict,
        "usable_for_pruning": verdict == "usable",
        "reasons": reasons,
        "totals": {
            "dispatches": total_dispatches,
            "logged": total_logged,
            "value_rows": len(value_rows),
            "coverage": coverage,
            "noop_share": share,
        },
        "per_lens": per_lens,
    }


def run(cwd: Path) -> dict:
    value_rows, value_malformed = read_jsonl(_resolve(VALUE_STREAM, cwd))
    ledger_rows, ledger_malformed = read_jsonl(_resolve(LEDGER_STREAM, cwd))
    report = assess(value_rows, ledger_rows)
    report["malformed_lines"] = {
        VALUE_STREAM: value_malformed,
        LEDGER_STREAM: ledger_malformed,
    }
    return report


def _format_text(report: dict) -> str:
    totals = report["totals"]
    lines = [f"review-value sample: {report['verdict'].upper()}"]
    cov = totals["coverage"]
    share = totals["noop_share"]
    lines.append(
        f"  rows={totals['value_rows']} dispatches={totals['dispatches']} "
        f"logged={totals['logged']} "
        f"coverage={'n/a' if cov is None else f'{cov:.0%}'} "
        f"no-op={'n/a' if share is None else f'{share:.0%}'}"
    )
    for reason in report["reasons"]:
        lines.append(f"  - {reason}")
    if not report["usable_for_pruning"]:
        lines.append(
            "  VERDICT: do not cite per-lens value from this sample (#2019)."
        )
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Report whether .claude/metrics/review-value.jsonl can support a "
            "per-lens pruning decision. Consult before citing per-lens value."
        )
    )
    parser.add_argument("--cwd", default=None)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 when the sample cannot support a pruning decision",
    )
    args = parser.parse_args(argv)

    report = run(Path(args.cwd) if args.cwd else Path.cwd())
    if args.as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(_format_text(report))
    return 1 if args.strict and not report["usable_for_pruning"] else 0


if __name__ == "__main__":
    sys.exit(main())
