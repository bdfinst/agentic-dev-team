#!/usr/bin/env python3
"""Compare an agent's frontmatter model/effort (baseline) with a candidate.

Runs each trial through `claude -p` with the agent's read-only built-in tools
(plus its write tools under Claude Code's Bash sandbox, for an agent
evals/model-effort/graders.json marks `sandbox: true`) against a fresh copy of a
fixture, grades it with the agent's grader from that map, and
writes one JSON artifact per run to the runs directory. The fixtures, their
expected entries and the knowledge directory are copied once when the run is
planned, so editing them mid-run changes nothing. Trials alternate
baseline, candidate, baseline, ... so a broken candidate fails on its first trial.

With --stress the arms are the frontmatter tier, one step down and one step up,
and the artifact records a downgrade/upgrade/keep verdict. --batch <tier> runs
--stress for every agent at that frontmatter model tier, after one combined
estimate (rubric judge included) and one approval; it stops at the first run
that does not complete.

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
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

# The only sys.path bootstrap: it makes the `model_effort` package importable.
_PACKAGE_PARENT = Path(__file__).resolve().parent / "lib"
if str(_PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_PARENT))

from model_effort import (
    answer_key,
    batch,
    check_jail,
    external,
    interrupts,
    invocation,
    paths,
    report,
    rubric_judge,
    runner,
    session,
)
from model_effort.errors import UsageError
from model_effort.execution import TrialRunner
from model_effort.judge_tier import MODEL_TIERS
from model_effort.plan import RunPlan, plan_run
from model_effort.run_types import TrialSettings
from model_effort.session import EXIT_FAILED, EXIT_USAGE
from model_effort.stop_rules import SpendLimit
from model_effort.stress_arms import Axis
from model_effort.trial_count import (
    DEFAULT_TRIALS,
    HIGH_STAKES_AGENTS,
    HIGH_STAKES_TRIALS,
    RUBRIC_TRIALS,
    resolve_trials,
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
    run_judge_process: rubric_judge.ProcessRunner = runner.run_cli_process
    find_check_jail: Callable[[], check_jail.CheckJail | None] = (
        check_jail.find_working_jail
    )
    find_answer_key_paths: Callable[[], tuple[Path, ...]] = (
        answer_key.repo_answer_key_paths
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="model_effort_ab.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "agent",
        nargs="?",
        help="agent name, as in plugins/dev-team/agents/<agent>.md (omit with --batch)",
    )
    parser.add_argument(
        "--batch",
        choices=MODEL_TIERS,
        help="stress batch: a --stress run for every agent whose frontmatter model is "
        "this tier, with one combined estimate (rubric judge included) and one "
        "approval; agents that cannot run are listed as skipped",
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
        "--stress",
        action="store_true",
        help="stress-matrix run: the frontmatter tier, one step down and one step up "
        "(see --axis), with a downgrade/upgrade/keep verdict in the artifact; "
        "cannot be combined with --model or --effort",
    )
    parser.add_argument(
        "--axis",
        type=Axis,
        choices=list(Axis),
        default=Axis.MODEL,
        help="ladder a --stress step moves on first: model (haiku, sonnet, opus) or "
        "effort (low ... max); a step with no rung left there moves on the other "
        "ladder (default: model)",
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
        f"{', '.join(sorted(HIGH_STAKES_AGENTS))}; {RUBRIC_TRIALS} for rubric-judged "
        f"agents; otherwise {DEFAULT_TRIALS}). The grader per agent comes from "
        "evals/model-effort/graders.json",
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
        help="dollars; refuse to run when the estimate (rubric judge included) is "
        "above this, and stop the run once the charged cost is above this: each "
        "trial's and each rubric judgement's reported cost, or its estimate when it "
        "reported none (no default)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="start without the confirmation prompt (required when stdin is not a TTY)",
    )
    parser.add_argument(
        "--allow-unjailed-checks",
        action="store_true",
        help="run a fixture's test commands (agent-written code) without a jail when "
        "no working sandbox-exec (macOS) or bwrap (Linux) is found; use only on a "
        "disposable machine",
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


def _settings_for(args: argparse.Namespace, plan: RunPlan) -> TrialSettings:
    return TrialSettings(
        trials=resolve_trials(args.trials, plan.agent, plan.grading.kind),
        trial_timeout_seconds=args.trial_timeout_seconds,
        claude_bin=args.claude_bin,
    )


def _check_target(args: argparse.Namespace) -> None:
    if args.batch is None and args.agent is None:
        raise UsageError("name an agent, or pass --batch haiku|sonnet|opus")
    if args.batch is None:
        return
    if args.agent is not None:
        raise UsageError("--batch runs every agent at its tier: drop the agent name")
    if args.model or args.effort or args.fixture_stems:
        raise UsageError(
            "--batch picks each agent's arms and fixtures: drop --model, --effort "
            "and --fixtures"
        )


def _run(args: argparse.Namespace, deps: Deps, guard: interrupts.RunGuard) -> int:
    try:
        _check_target(args)
        console = session.Console(deps.stdin, deps.stdin_is_tty, sys.stdout, sys.stderr)
        spend_limit = (
            SpendLimit(args.max_cost_usd) if args.max_cost_usd is not None else None
        )
        if args.batch is not None:
            return _run_batch(args, deps, guard, console, spend_limit)
        with _plan_from(args, deps) as plan:
            settings = _settings_for(args, plan)
            return session.run_session(
                plan,
                settings,
                spend_limit,
                console,
                assume_yes=args.yes,
                pricing_table=deps.pricing_table,
                run_trial=deps.run_trial,
                run_judge_process=deps.run_judge_process,
                guard=guard,
            )
    except UsageError as error:
        return _report_usage_error(error)


def _run_batch(
    args: argparse.Namespace,
    deps: Deps,
    guard: interrupts.RunGuard,
    console: session.Console,
    spend_limit: SpendLimit | None,
) -> int:
    stress_args = argparse.Namespace(**{**vars(args), "stress": True})

    def plan_agent(agent: str) -> AbstractContextManager[RunPlan]:
        return _plan_from(stress_args, deps, agent)

    with batch.plan_batch(
        args.batch, deps.eval_paths.agents_dir, plan_agent
    ) as planned:
        return batch.run_batch(
            planned,
            lambda plan: _settings_for(args, plan),
            spend_limit,
            console,
            assume_yes=args.yes,
            pricing_table=deps.pricing_table,
            run_trial=deps.run_trial,
            run_judge_process=deps.run_judge_process,
            guard=guard,
        )


def _plan_from(
    args: argparse.Namespace, deps: Deps, agent: str | None = None
) -> AbstractContextManager[RunPlan]:
    return plan_run(
        agent or args.agent,
        candidate_model=args.model,
        candidate_effort=args.effort,
        fixture_stems=_split_csv(args.fixture_stems),
        runs_dir=args.runs_dir,
        now=deps.clock(),
        rng=deps.rng,
        git_sha=deps.read_git_sha(),
        eval_paths=deps.eval_paths,
        allow_unjailed_checks=args.allow_unjailed_checks,
        find_check_jail=deps.find_check_jail,
        find_answer_key_paths=deps.find_answer_key_paths,
        stress_axis=args.axis if args.stress else None,
    )


def _report_usage_error(error: UsageError) -> int:
    print(f"error: {error}", file=sys.stderr)
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
