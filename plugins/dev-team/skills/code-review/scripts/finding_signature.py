#!/usr/bin/env python3
"""Finding identity across review rounds — the round ledger (#1625).

`/code-review`'s fix loop has an iteration cap but no notion of finding
*identity* across rounds: nothing can tell "this round found the same problem
again" from "this round found something genuinely new", so nothing can detect
that the loop is churning. #1619's case study ran 9 dispatch rounds over ~4
files, several of them re-verifying fixes to defects the previous round's fix
had introduced.

This module mirrors `/build`'s failure-signature dead-end detection (#864) —
the same normalize / compare / terminate pattern, applied to review findings —
and is the single shared implementation for both `/code-review`'s step 6a
loop and `/build`'s inline checkpoint loops.

## Why the line number is not inside the hash

The design sketch describes the signature as a tuple including a
"line-bucket ±3". A hashed bucket (`line // 7`) is *not* the same relation:
two reports of the same finding at lines 6 and 7 land in different buckets
and would read as two distinct findings, which is exactly the false-new
result the severity floor and loop-until-dry rules must not get. Proximity
is not an equivalence relation, so it cannot be folded into a hash without
introducing boundary artifacts.

So `signature()` hashes the *stable* identity — agent, file, category,
and the normalized message — and the line is carried alongside it in
`FindingKey`. `same_finding()` then applies the true ±`LINE_TOLERANCE`
proximity test. Callers that want one hashable key for set membership use
`FindingKey.signature`; callers deciding new-vs-carried use
`match_carried()`, which is the one that respects the tolerance.

## Message normalization

Volatile text is stripped before hashing so a finding re-reported after an
unrelated fix keeps its identity:

- line/column references (`:120:4`, `line 120`, `L120`)
- ISO-8601 timestamps
- hex digests of 7+ chars (commit shas, content hashes)
- quoted spans (`'x'`, `"x"`, `` `x` ``) — an identifier the fix renamed must
  not read as a different finding
- whitespace runs and letter case

Stdlib-only. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from typing import NamedTuple

#: Two reports of the same normalized finding within this many lines of each
#: other are the same finding. Fixes shift line numbers slightly; a finding
#: that moved further than this is treated as new, which is the conservative
#: direction (an extra round is cheaper than terminating on an unfixed defect).
LINE_TOLERANCE = 3

#: Severities that justify another fix-dispatch round from round 2 onward.
ACTIONABLE_SEVERITIES = frozenset({"error", "warning"})

#: Confidences that justify another fix-dispatch round from round 2 onward.
ACTIONABLE_CONFIDENCES = frozenset({"high", "medium"})

#: Total dispatch rounds (initial panel + fix-loop rounds) after which the
#: loop escalates to a human with the round ledger as evidence. Applied to
#: #1619's case study this would have surfaced the churn at round 4 rather
#: than round 9.
MAX_ROUNDS = 4

_TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?")
_LINE_REF_RE = re.compile(r"(?::\d+(?::\d+)?\b)|(?:\bl(?:ine)?s?\.?\s*\d+(?:\s*[-,]\s*\d+)*)", re.IGNORECASE)
_HEX_RE = re.compile(r"\b[0-9a-f]{7,}\b", re.IGNORECASE)
_QUOTED_RE = re.compile(r"`[^`]*`|\"[^\"]*\"|'[^']*'")
_NUMBER_RE = re.compile(r"\b\d+\b")
_WS_RE = re.compile(r"\s+")


class FindingKey(NamedTuple):
    """A finding's identity: a stable hash plus the line it was reported at.

    `signature` is hashable and stable across rounds; `line` is compared with
    `LINE_TOLERANCE` rather than folded into the hash (see module docstring).
    """

    signature: str
    line: int


def normalize_message(message: str) -> str:
    """Strip volatile text from a finding message so the same problem hashes
    identically after a fix shifts lines or renames an identifier.

    Order matters: timestamps and hex digests are removed before the bare
    number sweep, so a sha or a date can't leave stray digit fragments behind.
    """
    text = str(message or "")
    text = _TIMESTAMP_RE.sub(" ", text)
    text = _HEX_RE.sub(" ", text)
    text = _QUOTED_RE.sub(" ", text)
    text = _LINE_REF_RE.sub(" ", text)
    text = _NUMBER_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text)
    return text.strip().lower()


def _normalize_path(value) -> str:
    text = str(value or "").replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def signature(finding: dict) -> str:
    """Stable identity hash for one finding: agent, file, category, and the
    normalized message. Deliberately excludes the line number.

    `category` is the canonical taxonomy field (#1639) — settled on `category`
    rather than `rule` because that is what the three agents on this contract
    already emitting one (`security-review`, `ai-provenance-review`,
    `spec-compliance-review`) already spell it as, so no existing agent needed
    to migrate. `rule` and `ruleId` remain accepted fallbacks for a finding
    shaped by a future agent or an external tool that uses the more
    conventional linter-rule name — never required, never the preferred
    spelling to emit.

    `smell` is also accepted (#1692): `test-smell-review` carries its
    taxonomy in a `smell` field per `review-agent-output-contract.md`'s
    "Documented per-agent extensions" section, not `category`/`rule`/
    `ruleId`. Without this fallback every `test-smell-review` finding hashed
    with an empty taxonomy segment, risking false "carried" collisions
    between genuinely different smells whose normalized messages happen to
    be similar within `same_finding()`'s line-proximity window. It sits
    between `category` and `rule` in the fallback chain — after the
    genuinely canonical field, before the linter-style fallbacks.
    """
    agent = str(finding.get("agent") or finding.get("agentName") or "")
    path = _normalize_path(finding.get("file"))
    category = str(
        finding.get("category")
        or finding.get("smell")
        or finding.get("rule")
        or finding.get("ruleId")
        or ""
    )
    message = normalize_message(finding.get("message"))
    payload = f"{agent.lower()}\x1f{path}\x1f{category.lower()}\x1f{message}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def finding_key(finding: dict) -> FindingKey:
    """`FindingKey` for one finding. A missing/unusable line becomes `0`,
    which still compares correctly (two line-less reports of the same
    normalized finding are within tolerance of each other)."""
    line = finding.get("line")
    if isinstance(line, bool) or not isinstance(line, int) or line < 0:
        line = 0
    return FindingKey(signature(finding), line)


def same_finding(a: FindingKey, b: FindingKey, tolerance: int = LINE_TOLERANCE) -> bool:
    """True when two keys denote the same finding: identical stable hash and
    lines within `tolerance`."""
    return a.signature == b.signature and abs(a.line - b.line) <= tolerance


def match_carried(key: FindingKey, prior_keys, tolerance: int = LINE_TOLERANCE):
    """Return the prior key this finding carries forward from, or `None` when
    it is genuinely new."""
    for prior in prior_keys:
        candidate = prior if isinstance(prior, FindingKey) else FindingKey(*prior)
        if same_finding(key, candidate, tolerance):
            return candidate
    return None


def is_actionable(finding: dict) -> bool:
    """The severity floor (rounds >= 2): only error/warning findings at
    high/medium confidence justify another fix-dispatch round.

    Round 1 keeps `/code-review` step 5b's existing actionability table
    unchanged — this predicate governs round 2 onward only, where the
    question is "does this finding justify paying for another round?" rather
    than "should this be fixed at all?". A suggestion-tier finding from a
    later round is still recorded and still written to `corrections/`; it
    just never triggers a re-dispatch.
    """
    severity = str(finding.get("severity", "")).lower()
    confidence = str(finding.get("confidence", "")).lower()
    return severity in ACTIONABLE_SEVERITIES and confidence in ACTIONABLE_CONFIDENCES


def classify_round(findings, prior_keys, round_number: int) -> dict:
    """Split one round's findings into new / carried, and decide whether the
    loop continues.

    Returns a dict with:
      `new`, `carried`      — finding lists
      `new_keys`            — `[[signature, line], ...]` for the durable ledger
      `all_keys`            — every key seen through this round (for the next call)
      `actionable_new`      — new findings clearing the severity floor
      `terminate`           — True when the loop must stop
      `reason`              — `converged` | `round-cap` | `null` (continue)

    Termination rules, first match wins (issue #1625 design item 3):

    1. **Hard round cap** — `round_number >= MAX_ROUNDS` escalates to a human
       with the ledger as evidence, whatever was found.
    2. **Loop-until-dry** — a round producing zero *new-signature* findings
       that clear the severity floor is converged. Carried signatures that
       survived a fix attempt are already handled by the existing "same
       issues persist -> escalate" exit, so they are not a reason to continue
       here.
    3. Otherwise the loop continues.

    Round 1 never terminates on rule 2 with findings outstanding: its
    actionability is step 5b's table, not this severity floor. Callers pass
    `round_number=1` for the initial panel and it is treated as continuing
    whenever any finding is actionable under either definition.
    """
    prior = [p if isinstance(p, FindingKey) else FindingKey(*p) for p in prior_keys]
    new, carried = [], []
    keys_this_round = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        key = finding_key(finding)
        keys_this_round.append(key)
        if match_carried(key, prior) is None:
            new.append(finding)
        else:
            carried.append(finding)

    actionable_new = [f for f in new if is_actionable(f)]

    if round_number >= MAX_ROUNDS:
        terminate, reason = True, "round-cap"
    elif not actionable_new:
        terminate, reason = True, "converged"
    else:
        terminate, reason = False, None

    seen = list(prior)
    for key in keys_this_round:
        if match_carried(key, seen) is None:
            seen.append(key)

    return {
        "round": round_number,
        "new": new,
        "carried": carried,
        "new_keys": [list(finding_key(f)) for f in new],
        "all_keys": [list(k) for k in seen],
        "actionable_new": actionable_new,
        "terminate": terminate,
        "reason": reason,
    }


#: A stored ledger older than this is discarded rather than reused. A review
#: run does not legitimately span a day; a state file that old is abandoned
#: residue, and reusing it would suppress genuinely-new findings as "carried"
#: against signatures from unrelated work.
STATE_TTL_SECONDS = 24 * 60 * 60


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _age_seconds(iso: str) -> float | None:
    from datetime import datetime, timezone

    try:
        stamp = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None
    return (datetime.now(timezone.utc) - stamp).total_seconds()


def _empty_state() -> dict:
    return {"rounds": [], "all_keys": [], "run_id": None, "started_at": None}


def _load_state(state_path, run_id, round_number: int, force_reset: bool):
    """Load the durable ledger, discarding it when it belongs to a different
    run. Returns `(state, reset_reason)`; `reset_reason` is `None` when a
    stored ledger was legitimately resumed.

    Four reset triggers, in precedence order — each one exists because
    reusing the ledger in that situation would silently misclassify a genuinely
    new finding as "carried" (suppressing a round that should have run) or
    inflate the round counter toward the cap on unrelated history:

    1. `--reset` — explicit.
    2. **Round 1** — the initial panel *is* the start of a new run by
       definition. This is the common case and needs no caller bookkeeping:
       `/code-review` always calls round 1 first, so an abandoned ledger from
       a previous review can never leak into the next one. `/continue`
       resuming mid-loop calls round >= 2 and correctly resumes.
    3. **`run_id` mismatch** — the stored ledger was built for a different
       changeset. Catches a resume that legitimately starts at round >= 2 but
       against different targets.
    4. **Staleness** — `STATE_TTL_SECONDS` since the run started.

    Fails toward a reset: an unreadable or malformed state file starts fresh
    rather than propagating a half-parsed ledger. Starting fresh only ever
    costs an extra round; reusing a wrong ledger silently skips one.
    """
    if state_path is None or not state_path.is_file():
        return _empty_state(), None

    if force_reset:
        return _empty_state(), "explicit-reset"
    if round_number <= 1:
        return _empty_state(), "new-run-round-1"

    try:
        stored = json.loads(state_path.read_text("utf-8"))
    except (OSError, ValueError):
        return _empty_state(), "unreadable-state"
    if not isinstance(stored, dict):
        return _empty_state(), "unreadable-state"

    if run_id is not None and stored.get("run_id") != run_id:
        return _empty_state(), "run-id-mismatch"

    age = _age_seconds(stored.get("started_at"))
    if age is not None and age > STATE_TTL_SECONDS:
        return _empty_state(), "stale-state"

    stored.setdefault("rounds", [])
    stored.setdefault("all_keys", [])
    return stored, None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Classify one review round's findings against the prior rounds' ledger."
    )
    parser.add_argument("--round", type=int, required=True, dest="round_number")
    parser.add_argument(
        "--findings", default="-", help="Path to this round's findings JSON; '-' for stdin"
    )
    parser.add_argument(
        "--state",
        default=None,
        help="Path to the durable round-ledger state file (read + rewritten in place)",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        dest="run_id",
        help=(
            "Stable identity for this review run (e.g. the digest of the sorted "
            "target-file list). A stored ledger with a different run_id belongs "
            "to another changeset and is discarded rather than reused."
        ),
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Discard any stored ledger and start a fresh run.",
    )
    args = parser.parse_args(argv)

    from pathlib import Path

    raw = sys.stdin.read() if args.findings == "-" else Path(args.findings).read_text("utf-8")
    data = json.loads(raw) if raw.strip() else []
    if isinstance(data, dict):
        data = data.get("findings", [])

    state_path = Path(args.state) if args.state else None
    state, reset_reason = _load_state(state_path, args.run_id, args.round_number, args.reset)

    result = classify_round(data, state.get("all_keys", []), args.round_number)

    if state_path is not None:
        state["all_keys"] = result["all_keys"]
        state["run_id"] = args.run_id
        # `setdefault` is wrong here: `_empty_state()` seeds an explicit None,
        # which setdefault would preserve — leaving every fresh run with no
        # start time and so permanently exempt from the staleness TTL.
        if not state.get("started_at"):
            state["started_at"] = _now_iso()
        state["updated_at"] = _now_iso()
        state.setdefault("rounds", []).append(
            {
                "round": result["round"],
                "new": len(result["new"]),
                "carried": len(result["carried"]),
                "actionable_new": len(result["actionable_new"]),
                "terminate": result["terminate"],
                "reason": result["reason"],
            }
        )
        try:
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", "utf-8")
        except OSError as exc:
            sys.stderr.write(f"[finding_signature] could not write {state_path}: {exc}\n")

    print(
        json.dumps(
            {
                "round": result["round"],
                "new": len(result["new"]),
                "carried": len(result["carried"]),
                "actionable_new": len(result["actionable_new"]),
                "ledger_reset": reset_reason,
                "terminate": result["terminate"],
                "reason": result["reason"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
