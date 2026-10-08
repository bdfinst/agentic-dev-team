"""One run from the operator's side: price it, ask approval, run the trials, write the artifact.

All text goes through the injected `Console`, so the flow can be driven without
touching the process's real streams.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from . import approval, artifact, artifact_store, config_echo, estimate, report
from .errors import UsageError
from .execution import RunResult, TrialProgress, TrialRunner, TrialSettings, run_trials
from .formatting import format_usd
from .plan import RunPlan
from .run_status import AbortReason
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
) -> int:
    """Run the plan from estimate to artifact and return the exit code.

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

    run = run_trials(
        plan,
        settings,
        run_estimate,
        run_trial=run_trial,
        spend_limit=spend_limit,
        on_trial=print_progress,
    )
    return finish_run(plan, run, run_estimate, console)


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
        settings.trials_per_fixture.count,
        pricing_table,
    )
    for line in config_echo.render_config(plan, settings, run_estimate):
        print(line, file=console.stderr)
    if spend_limit is not None and spend_limit.refuses(run_estimate.total_cost_usd):
        raise UsageError(
            f"estimated total {format_usd(run_estimate.total_cost_usd)} is above "
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

    The artifact is saved before anything is printed, so a failing or interrupted
    terminal cannot cost the paid results.
    """
    if run.started_trials == 0:
        print(report.render_no_trials_notice(), file=console.stderr)
        return EXIT_FAILED
    run, data, text = _assemble_artifact(plan, run, run_estimate)
    save_exit_code = save_artifact(plan.artifact_path, text, console)
    if not run.is_complete:
        print(report.render_stop_notice(run), file=console.stderr)
    for line in report.render_summary(artifact.read_arm_totals(data)):
        print(line, file=console.stderr)
    if save_exit_code == EXIT_OK:
        print(f"artifact written: {plan.artifact_path}", file=console.stderr)
    return save_exit_code if run.is_complete else EXIT_FAILED


def _assemble_artifact(
    plan: RunPlan, run: RunResult, run_estimate: estimate.RunEstimate
) -> tuple[RunResult, dict, str]:
    """Build and render the artifact; a Ctrl-C while doing so marks the run interrupted and builds again.

    Returns the run the artifact describes, which differs from `run` after an interrupt.
    """
    try:
        return (run, *_build_and_render(plan, run, run_estimate))
    except KeyboardInterrupt:
        interrupted = dataclasses.replace(run, abort_reason=AbortReason.INTERRUPT)
        return (interrupted, *_build_and_render(plan, interrupted, run_estimate))


def _build_and_render(
    plan: RunPlan, run: RunResult, run_estimate: estimate.RunEstimate
) -> tuple[dict, str]:
    data = artifact.build_artifact(
        plan.metadata, run.arm_runs, run_estimate, run.abort_reason
    )
    return data, artifact_store.render_artifact(data)


def save_artifact(path: Path, text: str, console: Console) -> int:
    """Write the artifact atomically; if the write fails or is interrupted, print the JSON.

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
    except BaseException:
        # A second Ctrl-C or a termination signal mid-write.
        console.stdout.write(text)
        raise
    return EXIT_OK
