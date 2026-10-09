#!/usr/bin/env python3
"""Compare an agent's frontmatter model/effort (baseline) with a candidate.

Runs each trial through `claude -p` with the agent's read-only built-in tools
against a fresh copy of a fixture, grades it against `evals/expected`, and
writes one JSON artifact per run to the runs directory. The fixtures, their
expected entries and the knowledge directory are copied once when the run is
planned, so editing them mid-run changes nothing. Trials alternate
baseline, candidate, baseline, ... so a broken candidate fails on its first trial.

Ctrl-C, SIGTERM and SIGHUP are held from the first trial until the artifact is saved:
one that arrives while a trial runs kills that trial and ends the run, keeping the
completed trials; one that arrives later starts no further trial and keeps every
completed one; the artifact is saved before the run exits. A SIGHUP the process
ignores (`nohup`) never stops the run.

Exit codes:
  0  the run completed and the artifact was written
  1  the run was declined, stopped early (spend limit, systemic failure, Ctrl-C or
     a termination signal, or an unexpected error; the artifact keeps the
     completed trials), a signal arrived while the finished run was being saved
     (the artifact is still written), or the artifact could not be written (its
     JSON is printed to stdout so paid results survive)
  2  usage error or pre-run refusal
Messages go to stderr.
"""

from __future__ import annotations

import argparse
import math
import random
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

# The only sys.path bootstrap: it makes the `model_effort` package importable.
_PACKAGE_PARENT = Path(__file__).resolve().parent / "lib"
if str(_PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_PARENT))

from model_effort import (
    artifact,
    artifact_store,
    external,
    interrupts,
    invocation,
    paths,
    report,
    runner,
    session,
)
from model_effort.errors import UsageError
from model_effort.execution import TrialRunner
from model_effort.plan import RunPlan, plan_run
from model_effort.run_types import TrialSettings
from model_effort.session import EXIT_FAILED, EXIT_USAGE
from model_effort.stop_rules import SpendLimit
from model_effort.trial_count import (
    DEFAULT_TRIALS,
    HIGH_STAKES_AGENTS,
    HIGH_STAKES_TRIALS,
    resolve_trials,
)

RUBRIC_GRADER = "rubric"
RUBRIC_GRADER_REFUSAL = (
    "--grader rubric is not implemented yet; rubric grading is planned: "
    f"omit --grader to use {artifact.GRADER}"
)


def _read_git_head_sha() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=paths.REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip() or None


def _stdin_is_tty() -> bool:
    return sys.stdin.isatty()


@dataclass(frozen=True)
class Deps:
    """Everything nondeterministic or environment-specific, so tests can inject it."""

    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    rng: random.Random = field(default_factory=random.Random)
    read_git_sha: Callable[[], str | None] = _read_git_head_sha
    eval_paths: paths.EvalPaths = field(default_factory=paths.EvalPaths.default)
    pricing_table: dict = field(
        default_factory=lambda: external.pricing().load_pricing(paths.PRICING_PATH)
    )
    stdin: TextIO = field(default_factory=lambda: sys.stdin)
    stdin_is_tty: Callable[[], bool] = _stdin_is_tty
    run_trial: TrialRunner = runner.run_trial


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="model_effort_ab.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "agent", help="agent name, as in plugins/dev-team/agents/<agent>.md"
    )
    parser.add_argument(
        "--model",
        help="candidate model alias (default: the agent's frontmatter `model:`; "
        "the candidate must differ from the frontmatter in --model or --effort)",
    )
    parser.add_argument(
        "--effort",
        help="candidate effort level (default: the agent's frontmatter `effort:`)",
    )
    parser.add_argument(
        "--fixtures",
        dest="fixture_stems",
        help="comma-separated fixture stems (default: every evals/expected/*.json "
        "entry that names the agent)",
    )
    parser.add_argument(
        "--trials",
        type=_positive_int,
        help=f"trials per arm per fixture (default: {HIGH_STAKES_TRIALS} for "
        f"{', '.join(sorted(HIGH_STAKES_AGENTS))}; otherwise {DEFAULT_TRIALS})",
    )
    parser.add_argument(
        "--grader",
        choices=(artifact.GRADER, RUBRIC_GRADER),
        default=artifact.GRADER,
        help=f"how trials are graded (default: {artifact.GRADER}, the deterministic "
        f"grader over evals/expected; {RUBRIC_GRADER} is not implemented yet)",
    )
    parser.add_argument(
        "--trial-timeout",
        type=_positive_int,
        dest="trial_timeout_seconds",
        default=runner.DEFAULT_TRIAL_TIMEOUT_SECONDS,
        help="seconds before a trial is killed and recorded as timeout "
        f"(default: {runner.DEFAULT_TRIAL_TIMEOUT_SECONDS})",
    )
    parser.add_argument(
        "--max-cost",
        type=_positive_float,
        dest="max_cost_usd",
        help="dollars; refuse to run when the estimate is above this, and stop the "
        "run once the charged cost (reported cost, or the estimate for a trial that "
        "reported none) is above this (no default)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="start without the confirmation prompt (required when stdin is not a TTY)",
    )
    parser.add_argument(
        "--claude-bin",
        default=invocation.DEFAULT_CLAUDE_BIN,
        help=f"claude executable to run (default: {invocation.DEFAULT_CLAUDE_BIN})",
    )
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=paths.RUNS_DIR,
        help="directory the artifact is written to "
        f"(default: {paths.RUNS_DIR.relative_to(paths.REPO_ROOT)})",
    )
    return parser


def _positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        value = 0
    if value < 1:
        raise argparse.ArgumentTypeError(
            f"{text!r} is not a positive integer: pass a whole number of 1 or more"
        )
    return value


def _positive_float(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        value = 0.0
    if not 0 < value < math.inf:
        raise argparse.ArgumentTypeError(f"{text!r} is not a positive number")
    return value


def _split_csv(text: str | None) -> list[str] | None:
    if text is None:
        return None
    return list(dict.fromkeys(part.strip() for part in text.split(",") if part.strip()))


def main(argv: Sequence[str] | None = None, *, deps: Deps | None = None) -> int:
    deps = deps or Deps()
    args = _build_parser().parse_args(argv)
    guard = interrupts.RunGuard()
    with interrupts.termination_as_interrupt():
        try:
            return _run(args, deps, guard)
        except KeyboardInterrupt:
            # The guard holds the signals for the whole run, so an interrupt reaches
            # here only before the run starts or after the session has reported.
            print(
                report.render_unhandled_interrupt(run_started=guard.started),
                file=sys.stderr,
            )
            return EXIT_FAILED


def _run(args: argparse.Namespace, deps: Deps, guard: interrupts.RunGuard) -> int:
    if args.grader == RUBRIC_GRADER:
        return _report_usage_error(UsageError(RUBRIC_GRADER_REFUSAL))
    try:
        plan = _plan_from(args, deps)
    except UsageError as error:
        return _report_usage_error(error)
    with plan.snapshot, artifact_store.release_if_unwritten(plan.artifact_path):
        settings = TrialSettings(
            trials=resolve_trials(args.trials, args.agent),
            trial_timeout_seconds=args.trial_timeout_seconds,
            claude_bin=args.claude_bin,
        )
        console = session.Console(deps.stdin, deps.stdin_is_tty, sys.stdout, sys.stderr)
        spend_limit = (
            SpendLimit(args.max_cost_usd) if args.max_cost_usd is not None else None
        )
        try:
            return session.run_session(
                plan,
                settings,
                spend_limit,
                console,
                assume_yes=args.yes,
                pricing_table=deps.pricing_table,
                run_trial=deps.run_trial,
                guard=guard,
            )
        except UsageError as error:
            return _report_usage_error(error)


def _plan_from(args: argparse.Namespace, deps: Deps) -> RunPlan:
    return plan_run(
        args.agent,
        candidate_model=args.model,
        candidate_effort=args.effort,
        fixture_stems=_split_csv(args.fixture_stems),
        runs_dir=args.runs_dir,
        now=deps.clock(),
        rng=deps.rng,
        git_sha=deps.read_git_sha(),
        eval_paths=deps.eval_paths,
    )


def _report_usage_error(error: UsageError) -> int:
    print(f"error: {error}", file=sys.stderr)
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
