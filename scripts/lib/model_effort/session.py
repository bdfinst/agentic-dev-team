"""One run from the operator's side: price it, ask approval, run the trials, write the artifact.

All text goes through the injected `Console`, so the flow can be driven without
touching the process's real streams.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from . import (
    approval,
    arm_totals,
    artifact,
    artifact_store,
    config_echo,
    estimate,
    interrupts,
    report,
)
from .errors import UsageError
from .execution import TrialRunner, run_trials
from .formatting import format_usd
from .plan import RunPlan
from .run_types import RunResult, TrialProgress, TrialSettings
from .stop_rules import SpendLimit

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2


@dataclass(frozen=True)
class Console:
    """The operator's terminal: where approval is read from and messages are written."""

    stdin: TextIO
    stdin_is_tty: Callable[[], bool]
    stdout: TextIO
    stderr: TextIO


def run_session(
    plan: RunPlan,
    settings: TrialSettings,
    spend_limit: SpendLimit | None,
    console: Console,
    *,
    assume_yes: bool,
    pricing_table: dict,
    run_trial: TrialRunner,
    on_run_start: Callable[[], None] = lambda: None,
) -> int:
    """Run the plan from estimate to artifact and return the exit code.

    The interrupt signals are held from just before the first trial until the
    artifact is saved and the summary printed; `on_run_start` is called once
    they are held. One that arrives while the finished run is being saved, or as
    the signals are released, turns a clean exit into `EXIT_FAILED` after the
    save. One that arrives after this returns is the caller's to report.

    Raises:
        UsageError: a model is unpriced, or the estimate is above `spend_limit`.
    """
    run_estimate = estimate_and_echo(
        plan, settings, spend_limit, pricing_table, console
    )
    refusal = approval.refusal_unless_approved(
        assume_yes=assume_yes,
        stdin=console.stdin,
        stdin_is_tty=console.stdin_is_tty,
        stderr=console.stderr,
    )
    if refusal is not None:
        print(f"error: {refusal}", file=console.stderr)
        return EXIT_FAILED

    def print_progress(progress: TrialProgress) -> None:
        print(report.render_progress(progress), file=console.stderr)

    # Held from just before the first trial until the artifact is saved and the
    # summary printed, so a signal cannot cost a paid result. See `interrupts`.
    previous_mask = interrupts.block()
    on_run_start()
    exit_code = EXIT_FAILED
    try:
        try:
            run = run_trials(
                plan,
                settings,
                run_estimate,
                run_trial=run_trial,
                spend_limit=spend_limit,
                on_trial=print_progress,
            )
            exit_code = finish_run(plan, run, run_estimate, console)
        finally:
            interrupted_while_finishing = interrupts.restore_reporting(previous_mask)
    except KeyboardInterrupt:
        # The signals are free again, so one landing now is raised, not held. The
        # run is over and saved: count it as arriving while finishing.
        interrupted_while_finishing = True
    if interrupted_while_finishing and exit_code == EXIT_OK:
        print(
            "error: interrupted while finishing the run: the artifact was written "
            f"to {plan.artifact_path}",
            file=console.stderr,
        )
        return EXIT_FAILED
    return exit_code


def estimate_and_echo(
    plan: RunPlan,
    settings: TrialSettings,
    spend_limit: SpendLimit | None,
    pricing_table: dict,
    console: Console,
) -> estimate.RunEstimate:
    """Price the run, print the configuration and estimate, then enforce the spend limit.

    The echo comes before the limit check so a refused run still shows the figures.

    Raises:
        UsageError: a model is unpriced, or the estimate is above `spend_limit`.
    """
    run_estimate = estimate.estimate_run(
        plan.arms,
        plan.system_prompt,
        plan.fixtures,
        settings.trials.count,
        pricing_table,
    )
    for line in config_echo.render_config(plan, settings, run_estimate):
        print(line, file=console.stderr)
    if spend_limit is not None and spend_limit.refuses(
        run_estimate.estimated_total_usd
    ):
        raise UsageError(
            f"estimated total {format_usd(run_estimate.estimated_total_usd)} is above "
            f"--max-cost {format_usd(spend_limit.max_cost_usd)}: raise --max-cost, "
            "or lower --trials or --fixtures"
        )
    return run_estimate


def finish_run(
    plan: RunPlan,
    run: RunResult,
    run_estimate: estimate.RunEstimate,
    console: Console,
) -> int:
    """Write the artifact for a run that started a trial, report, and pick the exit code.

    The caller holds the interrupt signals until this returns, so the artifact is
    built, rendered and saved once, and describes the run as it ended. It is saved
    before anything is printed, so a failing terminal cannot cost the paid results.
    """
    if run.started_trials == 0:
        print(report.render_no_trials_notice(), file=console.stderr)
        return EXIT_FAILED
    data = artifact.build_artifact(
        plan.metadata, run.arm_runs, run_estimate, run.abort_reason
    )
    save_exit_code = save_artifact(
        plan.artifact_path, artifact_store.render_artifact(data), console
    )
    if not run.is_complete:
        print(report.render_stop_notice(run), file=console.stderr)
    summary = report.render_summary(
        [
            arm_totals.compute_arm_totals(arm_run, run_estimate)
            for arm_run in run.arm_runs
        ]
    )
    for line in summary:
        print(line, file=console.stderr)
    if save_exit_code == EXIT_OK:
        print(f"artifact written: {plan.artifact_path}", file=console.stderr)
    return save_exit_code if run.is_complete else EXIT_FAILED


def save_artifact(path: Path, text: str, console: Console) -> int:
    """Write the artifact atomically; if the write fails, print the JSON.

    The trials are paid for, so their results must survive a failed write.
    """
    try:
        artifact_store.write_artifact(path, text)
    except OSError as error:
        console.stdout.write(text)
        print(
            f"error: cannot write artifact {path}: {error}. The trials ran; the artifact "
            f"JSON is on stdout. Save it to a new file in {path.parent}.",
            file=console.stderr,
        )
        return EXIT_FAILED
    return EXIT_OK
