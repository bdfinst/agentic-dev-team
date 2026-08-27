#!/usr/bin/env python3
"""Agent-vs-tool redundancy criterion for /harness-audit (#1983 Part 2).

The spike behind this issue found a seam: `/harness-audit` measures review
agents against *usage* data (fix rates, finding rates — Step 4), but has no
criterion that catches "this lens is redundant with a deterministic tool
that already covers the same lines." This module is that criterion, made
computable rather than left as intuition.

The criterion, precisely: a lens is a **redundancy candidate** for a round
when every one of its *applied* findings that round falls within
`tolerance` lines of a finding the deterministic static-analysis pre-pass
(`skills/static-analysis-integration/SKILL.md`, including its lizard/jscpd
adapters — #1974) already reported for the same file, in the same round. A
round where the lens found *nothing* is not evidence either way (a quiet
lens might just have had nothing to find) and is excluded from both the
redundant and non-redundant counts, mirroring `/harness-audit` Step 4's own
"exclude read-only rows" and "state the sample size" small-N honesty rules.

## Data sources — read this before wiring a caller

`review-value.jsonl` rows alone CANNOT drive this criterion. Its own schema
doc is explicit: rows carry "counts and outcomes only, never code or file
content" (`knowledge/telemetry-schema.md` -> `review-value.jsonl`) — there
is no `file`/`line` on a row to compare against anything. This criterion
instead needs, for the SAME round:

1. **A lens's applied findings** (`file`, `line` pairs) — from
   `/code-review --json`'s aggregated payload, `agents[].issues[]`
   (`skills/code-review/output-format.md`). Today this is only available
   from a **saved raw artifact** of a `--json` dispatch — e.g. a
   `code-review-benchmark` harness run's `results/raw/*.txt`
   (`evals/code-review-benchmark/README.md`), or a `--json` capture an
   operator saved by hand. It is NOT persisted by any committed metrics
   stream today.
2. **The deterministic pre-pass envelope for that same round** — the
   unified finding envelope `static-analysis-integration`'s Step 6 returns
   (`findings[]`, each `{file, line, rule_id, metadata: {source}}` —
   `knowledge/security-primitives-contract.md`). Also not persisted; it is
   the return value of the pre-pass step that ran alongside the round in
   question.

So this criterion runs against **saved-or-live per-round artifacts**, not a
`jq` query over a committed JSONL file the way the rest of this skill's
Step 4 does. Until (if ever) a caller persists both of those per round,
"run `/harness-audit`'s Step 4c" means: collect a handful of real rounds'
raw `/code-review --json` output plus their pre-pass envelope (the
code-review-benchmark harness's `raw/` directory is the most direct source
today), then feed them to `classify_lens_redundancy()`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

DEFAULT_TOLERANCE = 3
DEFAULT_MIN_ROUNDS = 5


def _finding_is_covered(
    finding: dict[str, Any],
    pretool_findings: list[dict[str, Any]],
    tolerance: int,
) -> bool:
    """True when some pre-pass finding names the same file within
    `tolerance` lines of `finding`. A finding with no `file`/`line` can
    never be covered — fail-safe toward "not redundant"."""
    f_file = finding.get("file")
    f_line = finding.get("line")
    if f_file is None or f_line is None:
        return False
    for pt in pretool_findings:
        if pt.get("file") != f_file:
            continue
        pt_line = pt.get("line")
        if pt_line is None:
            continue
        try:
            if abs(int(f_line) - int(pt_line)) <= tolerance:
                return True
        except (TypeError, ValueError):
            continue
    return False


def is_round_redundant(
    applied_findings: list[dict[str, Any]],
    pretool_findings: list[dict[str, Any]],
    tolerance: int = DEFAULT_TOLERANCE,
) -> bool | None:
    """One round's subset-redundancy verdict for one lens.

    Returns `True` when every applied finding is covered by the pre-pass
    envelope (a fully-subsumed round — a candidate data point for
    redundancy), `False` when at least one applied finding is NOT covered
    (the lens found something the tool didn't — direct evidence AGAINST
    redundancy), and `None` when the lens applied no findings this round
    (a no-op round proves nothing about redundancy either way, so it is
    excluded rather than silently counted as "redundant" — the same
    "no-op is not evidence" discipline Step 4's fix-rate exclusions apply).
    """
    if not applied_findings:
        return None
    return all(
        _finding_is_covered(f, pretool_findings, tolerance) for f in applied_findings
    )


def classify_lens_redundancy(
    rounds: list[dict[str, Any]],
    tolerance: int = DEFAULT_TOLERANCE,
    min_rounds: int = DEFAULT_MIN_ROUNDS,
) -> dict[str, Any]:
    """Aggregate one lens's per-round subset-redundancy verdicts.

    `rounds`: a list of `{"applied_findings": [...], "pretool_findings":
    [...]}` dicts, one per round this lens ran in, for a single lens.

    Verdicts:
      - `insufficient-data` — fewer than `min_rounds` rounds where the lens
        found anything at all (the only kind of round this criterion can
        judge). Never a redundancy claim on too little evidence — mirrors
        Step 4's own "N >= 5" drop-candidate floor.
      - `redundant-candidate` — every judged round was fully subsumed by
        the pre-pass tool.
      - `not-redundant` — at least one judged round found something the
        pre-pass tool did not.
    """
    verdicts = [
        is_round_redundant(r["applied_findings"], r["pretool_findings"], tolerance)
        for r in rounds
    ]
    judged = [v for v in verdicts if v is not None]
    no_op_rounds = len(verdicts) - len(judged)
    redundant_rounds = sum(1 for v in judged if v)

    if len(judged) < min_rounds:
        verdict = "insufficient-data"
    elif redundant_rounds == len(judged):
        verdict = "redundant-candidate"
    else:
        verdict = "not-redundant"

    return {
        "verdict": verdict,
        "rounds_total": len(rounds),
        "rounds_with_findings": len(judged),
        "rounds_no_op": no_op_rounds,
        "rounds_fully_subsumed": redundant_rounds,
        "tolerance": tolerance,
        "min_rounds": min_rounds,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rounds",
        required=True,
        help=(
            "Path to a JSON file: a list of {\"applied_findings\": [...], "
            "\"pretool_findings\": [...]} round records for ONE lens."
        ),
    )
    parser.add_argument("--tolerance", type=int, default=DEFAULT_TOLERANCE)
    parser.add_argument("--min-rounds", type=int, default=DEFAULT_MIN_ROUNDS)
    args = parser.parse_args(argv)

    rounds_path = Path(args.rounds)
    try:
        rounds = json.loads(rounds_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"redundancy_criterion: cannot read {rounds_path}: {exc}", file=sys.stderr)
        return 1

    result = classify_lens_redundancy(
        rounds, tolerance=args.tolerance, min_rounds=args.min_rounds
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
