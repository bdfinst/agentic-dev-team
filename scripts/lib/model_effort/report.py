"""Render what the operator sees while a run is going and after it ends: progress, stop notices, summary."""

from __future__ import annotations

from collections.abc import Sequence

from .artifact import ArmTotals
from .cost import total_cost_usd
from .execution import RunResult, TrialProgress
from .formatting import escape_unprintable, format_usd
from .run_status import AbortReason

NO_ERROR_TEXT = "no error text was recorded"


def render_progress(progress: TrialProgress) -> str:
    """One line per completed trial: arm, fixture, trial number, outcome and cost."""
    result = progress.result
    return (
        f"[{progress.arm_label}] fixture {progress.fixture_number}/{progress.fixture_count} "
        f"{progress.fixture_stem} trial {progress.trial_number}/{progress.trial_count}: "
        f"{result.outcome.value} {format_usd(result.cost_usd)}"
    )


def render_stop_notice(run: RunResult) -> str:
    """Name why the run ended early and what the operator can do about it.

    Raises:
        ValueError: the run was not aborted.
    """
    if run.is_complete:
        raise ValueError("run was not aborted, so there is no stop to report")
    reason = run.abort_reason
    if reason is AbortReason.MAX_COST:
        return (
            f"error: run stopped early ({reason.value}): actual cost passed "
            "--max-cost; raise --max-cost to run the rest"
        )
    if reason is AbortReason.INFRA_FAILURE and run.stopping_trial is not None:
        trial = run.stopping_trial
        cause = escape_unprintable(trial.result.error or NO_ERROR_TEXT)
        return (
            f"error: run stopped early ({reason.value}): the {trial.arm_label} arm ended in "
            f"{trial.result.outcome.value}. Likely cause: {cause}. "
            "Fix that and rerun"
        )
    if reason is AbortReason.INTERRUPT:
        return (
            f"error: run stopped early ({reason.value}): the trial in flight was "
            f"dropped; {run.completed_trials} completed trials were kept"
        )
    if reason is AbortReason.HARNESS_ERROR:
        return (
            f"error: run stopped early ({reason.value}): "
            f"{escape_unprintable(run.harness_error or '')}. "
            f"{run.completed_trials} completed trials were kept; fix that and rerun"
        )
    raise ValueError(f"run stopped for a reason with no notice: {reason!r}")


def render_no_trials_notice() -> str:
    return (
        "error: interrupted before any trial started, so no artifact was written: "
        "rerun to start over"
    )


def render_summary(arms: Sequence[ArmTotals]) -> list[str]:
    """Per-arm outcome totals, then actual against estimated cost per arm and in total."""
    lines = ["Summary:"]
    for arm in arms:
        counts = ", ".join(
            f"{outcome.value} {count}" for outcome, count in arm.outcome_counts.items()
        )
        cost_text = _render_cost(
            arm.actual_cost_usd, arm.estimated_cost_charged_usd, arm.estimated_cost_usd
        )
        lines.append(f"  {arm.label}: {counts}; {cost_text}")
    total = _render_cost(
        total_cost_usd(arm.actual_cost_usd for arm in arms),
        total_cost_usd(arm.estimated_cost_charged_usd for arm in arms),
        total_cost_usd(arm.estimated_cost_usd for arm in arms),
    )
    lines.append(f"  total: {total}")
    return lines


def _render_cost(actual_usd: float, charged_usd: float, estimated_usd: float) -> str:
    """Show the actual cost; flag it as a lower bound when trials reported no cost."""
    lower_bound = (
        f" (lower bound; {format_usd(charged_usd)} charged as estimate for trials "
        "with no reported cost)"
        if charged_usd > 0
        else ""
    )
    return (
        f"cost {format_usd(actual_usd)}{lower_bound}, "
        f"estimated {format_usd(estimated_usd)}"
    )
