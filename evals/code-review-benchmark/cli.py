#!/usr/bin/env python3
"""CLI entry point for the /code-review benchmark harness (#821).

Usage:
    python3 cli.py --dataset defects4j --project Lang --sample 5
    python3 cli.py --dataset bugsjs --project Bower --resume
    python3 cli.py --dataset defects4j --limit-projects 2 --full-repo
    python3 cli.py --dataset defects4j --project Lang --bug-ids 36,44,7
    python3 cli.py --dataset defects4j --max-cost-usd 50
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
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import report
import runner
import scheduler
from adapters import bootstrap, bugsjs_adapter, defects4j_adapter

DEFAULT_RESULTS_DIR = Path(__file__).resolve().parent / "results"

# #1000: conservative, hardcoded per-case cost estimate for the pre-sweep
# warning — rounded up from the $4.48 real-case high measured in #974, not
# extrapolated from live cases (see the plan's Decisions & Assumptions for
# why extrapolation was deferred).
DEFAULT_COST_PER_CASE_ESTIMATE_USD = 4.50


def _positive_float(raw: str) -> float:
    """`argparse` `type=` validator for `--max-cost-usd`: rejects `<= 0`
    rather than silently accepting an ambiguous "zero (or negative)
    budget" — mirrors `--dataset`'s `choices=` validation style (an
    `argparse` error, not a custom exception)."""
    value = float(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError(
            f"--max-cost-usd must be a positive number, got {raw!r}"
        )
    return value


def _parse_bug_ids(raw: Optional[str]) -> Optional[set]:
    """Parse `--bug-ids`' comma-separated string into a set of bug-id strings.

    `None` in, `None` out — distinguishes "flag not given" from "flag given
    with an (unlikely) empty value" for `_list_cases`' precedence check.
    """
    if raw is None:
        return None
    return {piece.strip() for piece in raw.split(",") if piece.strip()}


def _list_cases(
    dataset: str,
    home: str,
    project_filter: Optional[str],
    limit_projects: Optional[int],
    sample: Optional[int],
    bug_ids: Optional[set] = None,
) -> List[Any]:
    adapter = defects4j_adapter if dataset == "defects4j" else bugsjs_adapter
    projects = [project_filter] if project_filter else adapter.list_projects(home)
    if limit_projects is not None:
        projects = projects[:limit_projects]

    cases: List[Any] = []
    for project in projects:
        project_cases = adapter.list_bugs(project, home)
        if bug_ids is not None:
            # Explicit, deterministic selection takes precedence over
            # --sample's random thinning (#970) — the whole point is a
            # reproducible, pinned case set for verification sweeps.
            project_cases = [c for c in project_cases if c.bug_id in bug_ids]
        elif sample is not None and len(project_cases) > sample:
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

    if args.bug_ids and args.sample:
        print(
            "code-review-benchmark: --bug-ids given — ignoring --sample "
            "(explicit selection takes precedence).",
            file=sys.stderr,
        )

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
        args.dataset,
        home,
        args.project,
        args.limit_projects,
        args.sample,
        bug_ids=_parse_bug_ids(args.bug_ids),
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

    if pending:
        estimate = len(pending) * DEFAULT_COST_PER_CASE_ESTIMATE_USD
        print(
            f"code-review-benchmark: about to dispatch {len(pending)} case(s); "
            "prior measured per-case cost $1.29-$4.48 (#974) — conservative "
            f"estimate ${estimate:.2f} total. Use --max-cost-usd to cap spend.",
            file=sys.stderr,
        )

    def _make_kwargs(case: Any) -> Dict[str, Any]:
        return {
            "checkout_fn": _make_checkout_fn(
                args.dataset, case, home, defects4j_bin, defects4j_env
            ),
            "ground_truth_fn": _make_ground_truth_fn(args.dataset, case),
            "test_fn": _make_test_fn(
                args.dataset,
                case,
                not args.no_verify_tests,
                defects4j_bin,
                defects4j_env,
            ),
            "scope": "full-repo" if args.full_repo else "fix-only",
            "tolerance": args.tolerance,
        }

    total_cost = scheduler.run_pending(
        pending,
        make_kwargs=_make_kwargs,
        dispatch_fn=dispatch_fn,
        results_dir=results_dir,
        workers=args.workers,
        max_cost_usd=args.max_cost_usd,
    )

    path = report.write_report(results_dir)
    print(f"Wrote {path} (total cost: ${total_cost:.2f})")
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
        "--bug-ids",
        help=(
            "Comma-separated, explicit bug IDs to run (e.g. '36,44,7'). "
            "Deterministic — takes precedence over --sample for a "
            "reproducible verification sweep pinned to specific cases."
        ),
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
        "--max-cost-usd",
        type=_positive_float,
        default=None,
        help=(
            "Fail-safe spend cutoff, USD (#1000, default: no cap). Checked "
            "only AFTER a case completes — not before the initial "
            "--workers-sized batch is primed — so realized spend can "
            "exceed this by up to `workers - 1` extra in-flight cases' "
            "cost; the executor never cancels an in-flight case. Once "
            "reached, no further case is submitted; still-queued cases "
            "are recorded to skipped.jsonl (never silently dropped) and a "
            "clear message is printed to stderr. Must be > 0."
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
