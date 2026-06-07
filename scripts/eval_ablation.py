#!/usr/bin/env python3
"""Knowledge ablation analysis (#107).

Does a knowledge file earn its tokens? Run the eval corpus twice — once with the
file AVAILABLE, once ABLATED (hidden) — and diff the grades. Pairs that PASSED
with the knowledge but FAIL without it are the file's measured *retrieval value*.

This module is the deterministic, model-free half: given the two recorded actuals
(the live with/without runs are driven by run-ablation.sh), it grades both via
eval_grade and reports the impact. A file whose ablation drops nothing is a
removal/consolidation candidate.

Inputs
------
--expected-dir DIR   Expected specs (default: evals/expected).
--baseline FILE      Actuals from the run WITH the knowledge available.
--ablated FILE       Actuals from the run with the knowledge ablated.
--knowledge NAME     Label for the ablated file (reporting only).
--only AGENT         Restrict grading to one agent (optional).
-o FILE              Write the report (default: stdout).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_grade import run_grading  # noqa: E402


def _passing(expected_dir: Path, actuals: dict, only: set | None) -> set:
    results, _ = run_grading(expected_dir, actuals, None, only)
    return {pair for pair, passed, _ in results if passed}


def ablation_impact(expected_dir: Path, baseline: dict, ablated: dict,
                    knowledge: str = "", only: set | None = None) -> dict:
    """Pairs that pass WITH the knowledge but fail WITHOUT it = retrieval value."""
    base_pass = _passing(expected_dir, baseline, only)
    abl_pass = _passing(expected_dir, ablated, only)
    dropped = sorted(base_pass - abl_pass)   # depended on the knowledge
    gained = sorted(abl_pass - base_pass)     # noise: passed only without it
    return {
        "schema": "knowledge-ablation/v1",
        "knowledge": knowledge,
        "retrieval_value": len(dropped),      # how many pairs the file held up
        "dropped_pairs": dropped,             # the evidence
        "spurious_gains": gained,             # should be empty; flags noise
        "verdict": ("earns its place" if dropped else
                    "no measured impact — removal/consolidation candidate"),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--expected-dir", default="evals/expected")
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--ablated", required=True)
    ap.add_argument("--knowledge", default="")
    ap.add_argument("--only")
    ap.add_argument("-o", "--out")
    args = ap.parse_args(argv)

    baseline = json.loads(Path(args.baseline).read_text())
    ablated = json.loads(Path(args.ablated).read_text())
    only = {args.only} if args.only else None
    report = ablation_impact(Path(args.expected_dir), baseline, ablated,
                             args.knowledge, only)
    out = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(out + "\n")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
