#!/usr/bin/env python3
"""Compare an agent's frontmatter model/effort (baseline) with a candidate.

Runs each trial through `claude -p` with the agent's read-only built-in tools
against a fresh copy of a fixture, grades it against `evals/expected`, and
writes one JSON artifact per run to the runs directory. Trials alternate
baseline, candidate, baseline, ... so a broken candidate fails on its first trial.

Exit codes:
  0  the run completed and the artifact was written
  1  the run was declined, aborted or incomplete, or the artifact could not be
     written (its JSON is printed to stdout so paid results survive)
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

REPO_ROOT = Path(__file__).resolve().parents[1]
# The only sys.path bootstrap: the package imports `eval_grade` (scripts/) and `minimal_yaml`.
for _path in (
    REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib",
    REPO_ROOT / "scripts" / "lib",
    REPO_ROOT / "scripts",
):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import pricing
from model_effort import (
    approval,
    artifact,
    artifact_store,
    config_echo,
    estimate,
    paths,
    runner,
)
from model_effort.errors import UsageError
from model_effort.execution import TrialSettings, run_trials
from model_effort.plan import RunPlan, plan_run

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

DEFAULT_TRIALS = 5
TRIALS_DEFAULT_REASON = "default"
TRIALS_FLAG_REASON = "--trials"


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
    agents_dir: Path = paths.AGENTS_DIR
    expected_dir: Path = paths.EXPECTED_DIR
    fixtures_dir: Path = paths.FIXTURES_DIR
    pricing_table: dict = field(
        default_factory=lambda: pricing.load_pricing(paths.PRICING_PATH)
    )
    stdin: TextIO = field(default_factory=lambda: sys.stdin)
    stdin_is_tty: Callable[[], bool] = _stdin_is_tty


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
        help="candidate model alias (default: the agent's frontmatter `model:`)",
    )
    parser.add_argument(
        "--effort",
        help="candidate effort level (default: the agent's frontmatter `effort:`)",
    )
    parser.add_argument(
        "--fixtures",
        help="comma-separated fixture stems (default: every evals/expected/*.json "
        "entry that names the agent)",
    )
    parser.add_argument(
        "--trials",
        type=_positive_int,
        help=f"trials per arm per fixture (default: {DEFAULT_TRIALS})",
    )
    parser.add_argument(
        "--trial-timeout",
        type=_positive_int,
        default=runner.DEFAULT_TRIAL_TIMEOUT_SECONDS,
        help="seconds before a trial is killed and recorded as timeout "
        f"(default: {runner.DEFAULT_TRIAL_TIMEOUT_SECONDS})",
    )
    parser.add_argument(
        "--max-cost",
        type=_positive_float,
        help="refuse to run when the estimated total cost in dollars is above this "
        "(no default)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="start without the confirmation prompt (required when stdin is not a TTY)",
    )
    parser.add_argument(
        "--claude-bin",
        default=runner.DEFAULT_CLAUDE_BIN,
        help=f"claude executable to run (default: {runner.DEFAULT_CLAUDE_BIN})",
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
        raise argparse.ArgumentTypeError(f"{text!r} is not a positive integer")
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


def _save_artifact(path: Path, data: dict) -> int:
    """Write the artifact atomically; on any write error print the JSON so paid results survive."""
    text = artifact_store.render_artifact(data)
    try:
        artifact_store.write_artifact(path, text)
    except OSError as error:
        sys.stdout.write(text)
        print(
            f"error: cannot write artifact {path}: {error}. The trials ran; the artifact "
            f"JSON is on stdout. Save it to a new file in {path.parent}.",
            file=sys.stderr,
        )
        return EXIT_FAILED
    print(f"artifact written: {path}", file=sys.stderr)
    return EXIT_OK


def main(argv: Sequence[str] | None = None, *, deps: Deps | None = None) -> int:
    deps = deps or Deps()
    args = _build_parser().parse_args(argv)
    try:
        plan = plan_run(
            args.agent,
            candidate_model=args.model,
            candidate_effort=args.effort,
            fixture_stems=_split_csv(args.fixtures),
            runs_dir=args.runs_dir,
            now=deps.clock(),
            rng=deps.rng,
            git_sha=deps.read_git_sha(),
            agents_dir=deps.agents_dir,
            expected_dir=deps.expected_dir,
            fixtures_dir=deps.fixtures_dir,
        )
    except UsageError as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_USAGE
    trials = _resolve_trials(args.trials)
    settings = TrialSettings(
        trials=trials.count,
        trial_timeout=args.trial_timeout,
        claude_bin=args.claude_bin,
        expected_dir=deps.expected_dir,
    )
    with artifact_store.release_if_unwritten(plan.artifact_path):
        try:
            run_estimate = _estimate_and_echo(
                plan, settings, trials, args.max_cost, deps
            )
        except UsageError as error:
            print(f"error: {error}", file=sys.stderr)
            return EXIT_USAGE
        refusal = approval.request_approval(
            yes=args.yes,
            stdin=deps.stdin,
            stdin_is_tty=deps.stdin_is_tty,
            stderr=sys.stderr,
        )
        if refusal is not None:
            print(f"error: {refusal}", file=sys.stderr)
            return EXIT_FAILED
        arm_runs = run_trials(plan, settings, dict(run_estimate.by_arm))
        data = artifact.build_artifact(plan.metadata, arm_runs)
        return _save_artifact(plan.artifact_path, data)


def _resolve_trials(flag_value: int | None) -> config_echo.TrialCount:
    if flag_value is None:
        return config_echo.TrialCount(DEFAULT_TRIALS, TRIALS_DEFAULT_REASON)
    return config_echo.TrialCount(flag_value, TRIALS_FLAG_REASON)


def _estimate_and_echo(
    plan: RunPlan,
    settings: TrialSettings,
    trials: config_echo.TrialCount,
    max_cost: float | None,
    deps: Deps,
) -> estimate.RunEstimate:
    """Price the run, print the configuration and estimate, then enforce `--max-cost`.

    The echo comes before the limit check so a refused run still shows the figures.

    Raises:
        UsageError: a model is unpriced, or the estimate is above `max_cost`.
    """
    run_estimate = estimate.estimate_run(
        plan.arms, plan.system_prompt, plan.fixtures, trials.count, deps.pricing_table
    )
    for line in config_echo.render_config(
        plan, trials, settings.trial_timeout, run_estimate
    ):
        print(line, file=sys.stderr)
    if max_cost is not None and run_estimate.total_usd > max_cost:
        raise UsageError(
            f"estimated total {config_echo.format_usd(run_estimate.total_usd)} is above "
            f"--max-cost {config_echo.format_usd(max_cost)}: raise --max-cost, "
            "or lower --trials or --fixtures"
        )
    return run_estimate


if __name__ == "__main__":
    sys.exit(main())
