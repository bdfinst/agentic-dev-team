#!/usr/bin/env python3
"""CLI entry point for the /code-review benchmark harness (#821).

Usage:
    python3 cli.py --dataset defects4j --project Lang --sample 5
    python3 cli.py --dataset bugsjs --project Bower --resume
    python3 cli.py --dataset defects4j --limit-projects 2 --full-repo
    python3 cli.py --report-only

Prerequisites (not installed in this repo/sandbox — see README.md):
    Defects4J: `defects4j` on PATH, `--defects4j-home`/`DEFECTS4J_HOME` set to
    a full framework checkout.
    BugsJS: `--bugsjs-home`/`BUGSJS_HOME` set to a local clone of
    `BugsJS/bug-dataset`.
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import report
import runner
from adapters import bugsjs_adapter, defects4j_adapter

DEFAULT_RESULTS_DIR = Path(__file__).resolve().parent / "results"


def _list_cases(
    dataset: str,
    home: str,
    project_filter: Optional[str],
    limit_projects: Optional[int],
    sample: Optional[int],
) -> List[Any]:
    adapter = defects4j_adapter if dataset == "defects4j" else bugsjs_adapter
    projects = [project_filter] if project_filter else adapter.list_projects(home)
    if limit_projects is not None:
        projects = projects[:limit_projects]

    cases: List[Any] = []
    for project in projects:
        project_cases = adapter.list_bugs(project, home)
        if sample is not None and len(project_cases) > sample:
            project_cases = random.sample(project_cases, sample)
        cases.extend(project_cases)
    return cases


def _make_checkout_fn(dataset: str, case: Any, home: str):
    if dataset == "defects4j":
        return lambda workdir: defects4j_adapter.checkout(
            case, workdir, defects4j_home=home
        )
    return lambda workdir: bugsjs_adapter.checkout(case, workdir, bugsjs_home=home)


def _make_ground_truth_fn(dataset: str, case: Any):
    if dataset == "bugsjs":
        return lambda workdir: bugsjs_adapter.ground_truth(case, workdir)
    return None


def run(args: argparse.Namespace) -> int:
    results_dir = Path(args.results_dir)

    if args.report_only:
        path = report.write_report(results_dir)
        print(f"Wrote {path}")
        return 0

    home = (
        args.defects4j_home or os.environ.get("DEFECTS4J_HOME")
        if args.dataset == "defects4j"
        else args.bugsjs_home or os.environ.get("BUGSJS_HOME")
    )

    adapter = defects4j_adapter if args.dataset == "defects4j" else bugsjs_adapter
    if not adapter.detect(home):
        tool = (
            "defects4j (+ DEFECTS4J_HOME)"
            if args.dataset == "defects4j"
            else "BUGSJS_HOME"
        )
        print(
            f"code-review-benchmark: {tool} not available — see README.md prerequisites.",
            file=sys.stderr,
        )
        return 1

    cases = _list_cases(
        args.dataset, home, args.project, args.limit_projects, args.sample
    )
    if not cases:
        print(
            "code-review-benchmark: no bugs found for the given filters.",
            file=sys.stderr,
        )
        return 1

    already = runner.already_processed(results_dir) if args.resume else set()
    dispatch_fn = runner.make_isolated_dispatch_fn(
        model=args.model, timeout=args.timeout
    )

    processed = 0
    for case in cases:
        case_dict = case.to_dict()
        key = runner.case_key(case_dict)
        if key in already:
            continue

        record = runner.run_case(
            case_dict,
            checkout_fn=_make_checkout_fn(args.dataset, case, home),
            ground_truth_fn=_make_ground_truth_fn(args.dataset, case),
            dispatch_fn=dispatch_fn,
            results_dir=results_dir,
            scope="full-repo" if args.full_repo else "fix-only",
            tolerance=args.tolerance,
        )
        runner.append_result(record, results_dir)
        processed += 1
        status = (
            "HIT"
            if record.get("hit")
            else ("SKIP" if record.get("skipped") else "MISS")
        )
        print(f"[{processed}/{len(cases)}] {key}: {status}")

    path = report.write_report(results_dir)
    print(f"Wrote {path}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dataset", choices=["defects4j", "bugsjs"])
    parser.add_argument("--project", help="Filter to a single project.")
    parser.add_argument(
        "--sample", type=int, help="Random sample of N bugs per project."
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip cases already in results.jsonl/skipped.jsonl.",
    )
    parser.add_argument(
        "--full-repo",
        action="store_true",
        help="Review the whole checkout instead of just fix files.",
    )
    parser.add_argument(
        "--limit-projects", type=int, help="Cap the number of projects processed."
    )
    parser.add_argument(
        "--tolerance",
        type=int,
        default=runner.scorer.DEFAULT_TOLERANCE,
        help="Line-range tolerance for hit scoring.",
    )
    parser.add_argument(
        "--model",
        default="sonnet",
        help="Model tier passed to the /code-review dispatch.",
    )
    parser.add_argument(
        "--timeout", type=int, default=900, help="Per-case dispatch timeout, seconds."
    )
    parser.add_argument(
        "--defects4j-home", help="Defects4J framework checkout (or set DEFECTS4J_HOME)."
    )
    parser.add_argument(
        "--bugsjs-home", help="BugsJS/bug-dataset checkout (or set BUGSJS_HOME)."
    )
    parser.add_argument(
        "--results-dir",
        default=str(DEFAULT_RESULTS_DIR),
        help="Where results.jsonl/skipped.jsonl/report.md are written.",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Only (re)generate report.md from existing results.",
    )
    args = parser.parse_args(argv)

    if not args.report_only and not args.dataset:
        parser.error("--dataset is required unless --report-only is set")

    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
