#!/usr/bin/env python3
"""CLI entry point for the /code-review benchmark harness (#821).

Usage:
    python3 cli.py --dataset defects4j --project Lang --sample 5
    python3 cli.py --dataset bugsjs --project Bower --resume
    python3 cli.py --dataset defects4j --limit-projects 2 --full-repo
    python3 cli.py --report-only

Both dataset homes are auto-provisioned into a gitignored
`evals/code-review-benchmark/.cache/` on first use — see README.md — unless
`--defects4j-home`/`DEFECTS4J_HOME` or `--bugsjs-home`/`BUGSJS_HOME` points
at an existing checkout, in which case that's used as-is.
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import report
import runner
from adapters import bootstrap, bugsjs_adapter, defects4j_adapter

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


def _make_checkout_fn(
    dataset: str,
    case: Any,
    home: str,
    defects4j_bin: str = "defects4j",
    defects4j_env: Optional[Dict[str, str]] = None,
):
    if dataset == "defects4j":
        return lambda workdir: defects4j_adapter.checkout(
            case,
            workdir,
            defects4j_home=home,
            defects4j_bin=defects4j_bin,
            env=defects4j_env,
        )
    return lambda workdir: bugsjs_adapter.checkout(case, workdir, bugsjs_home=home)


def _make_ground_truth_fn(dataset: str, case: Any):
    if dataset == "bugsjs":
        return lambda workdir: bugsjs_adapter.ground_truth(case, workdir)
    return None


def _make_test_fn(
    dataset: str,
    case: Any,
    enabled: bool,
    defects4j_bin: str = "defects4j",
    defects4j_env: Optional[Dict[str, str]] = None,
) -> Optional[Callable[[str], Dict[str, Any]]]:
    """Build `run_case`'s `test_fn`, or `None` when verification is disabled.

    Diagnostic only (see runner.run_case) — never gates/skips a case.
    """
    if not enabled:
        return None
    if dataset == "defects4j":
        return lambda checkout_dir: defects4j_adapter.run_tests(
            case, checkout_dir, defects4j_bin=defects4j_bin, env=defects4j_env
        )
    return lambda checkout_dir: bugsjs_adapter.run_tests(case, checkout_dir)


def run(args: argparse.Namespace) -> int:
    results_dir = Path(args.results_dir)

    if args.report_only:
        path = report.write_report(results_dir)
        print(f"Wrote {path}")
        return 0

    defects4j_bin = "defects4j"
    defects4j_env: Optional[Dict[str, str]] = None
    if args.dataset == "defects4j":
        explicit_home = args.defects4j_home or os.environ.get("DEFECTS4J_HOME")
        resolved = bootstrap.ensure_defects4j_home(explicit_home)
        if resolved is None:
            print(
                "code-review-benchmark: could not auto-clone/initialize Defects4J "
                "— see README.md prerequisites.",
                file=sys.stderr,
            )
            return 1
        home = resolved["home"]
        defects4j_bin = resolved["bin"]
        defects4j_env = resolved["env"]
    else:
        explicit_home = args.bugsjs_home or os.environ.get("BUGSJS_HOME")
        cloned_home = bootstrap.ensure_bugsjs_home(explicit_home)
        if cloned_home is None:
            print(
                "code-review-benchmark: could not auto-clone BugsJS/bug-dataset "
                "— see README.md prerequisites.",
                file=sys.stderr,
            )
            return 1
        home = cloned_home

    adapter = defects4j_adapter if args.dataset == "defects4j" else bugsjs_adapter
    detect_ok = (
        adapter.detect(home, defects4j_bin)
        if args.dataset == "defects4j"
        else adapter.detect(home)
    )
    if not detect_ok:
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

    pending = []
    for case in cases:
        case_dict = case.to_dict()
        if runner.case_key(case_dict) in already:
            continue
        pending.append((case, case_dict))

    processed = 0
    total = len(pending)
    workers = max(1, args.workers)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                runner.run_case,
                case_dict,
                checkout_fn=_make_checkout_fn(
                    args.dataset, case, home, defects4j_bin, defects4j_env
                ),
                ground_truth_fn=_make_ground_truth_fn(args.dataset, case),
                test_fn=_make_test_fn(
                    args.dataset,
                    case,
                    not args.no_verify_tests,
                    defects4j_bin,
                    defects4j_env,
                ),
                dispatch_fn=dispatch_fn,
                results_dir=results_dir,
                scope="full-repo" if args.full_repo else "fix-only",
                tolerance=args.tolerance,
            ): case_dict
            for case, case_dict in pending
        }
        # Drain in the main thread as futures complete: keeps append_result()/
        # print() single-threaded (no lock needed) and isolates one case's
        # crash from aborting the rest of the batch.
        for future in as_completed(futures):
            case_dict = futures[future]
            key = runner.case_key(case_dict)
            try:
                record = future.result()
            except Exception as exc:  # noqa: BLE001 - one case's crash must not abort the batch
                record = runner.skip_record(case_dict, f"internal error: {exc}")

            runner.append_result(record, results_dir)
            processed += 1
            status = (
                "HIT"
                if record.get("hit")
                else ("SKIP" if record.get("skipped") else "MISS")
            )
            print(f"[{processed}/{total}] {key}: {status}")

    path = report.write_report(results_dir)
    print(f"Wrote {path}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    """Build this CLI's `argparse.ArgumentParser`, isolated from `main()` so
    tests can assert defaults/overrides (e.g. `--timeout`/`--workers`, #974)
    via `_build_parser().parse_args([...])` without exercising `run()`'s
    dataset auto-provisioning/detection."""
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
        "--timeout",
        type=int,
        default=1800,
        help=(
            "Per-case dispatch timeout, seconds (default 1800). Raised from "
            "900 after #974: a live single-file /code-review dispatch still "
            "fans out to the full ~14-agent review roster (scope narrows "
            "which files are reviewed, not how many agents run), measured "
            "at up to 58 turns / 846s cumulative API time / $4.48 for one "
            "real Defects4J case even at low concurrency — 900s was too "
            "tight a ceiling for that real cost, not evidence of a hang."
        ),
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=2,
        help=(
            "Number of bug cases to run concurrently, thread pool (default "
            "2). Lowered from 4 after #974: each case is really a ~14-20-"
            "way parallel agent fan-out under the hood, so 4 concurrent "
            "cases means up to ~60-80 concurrent nested `claude -p` "
            "dispatches sharing one host's CPU/network/rate limits — a "
            "plausible contributor to the 900s timeouts that motivated "
            "this change."
        ),
    )
    parser.add_argument(
        "--no-verify-tests",
        action="store_true",
        help=(
            "Skip building/installing deps and running the project's own "
            "test suite per case (on by default; diagnostic only, never "
            "gates scoring)."
        ),
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
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.report_only and not args.dataset:
        parser.error("--dataset is required unless --report-only is set")

    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
