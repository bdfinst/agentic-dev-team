"""Render the resolved run configuration and cost estimate as the lines printed before any trial."""

from __future__ import annotations

from .estimate import RunEstimate
from .formatting import format_usd
from .plan import RunPlan
from .run_types import TrialSettings

NO_TOOLS_TEXT = "no tools enabled"
NONE_TEXT = "none"


def render_config(
    plan: RunPlan, settings: TrialSettings, run_estimate: RunEstimate
) -> list[str]:
    profile = plan.profile
    arm_lines = [
        f"  {arm.label}: model {arm.model}, effort {arm.effort}" for arm in plan.arms
    ]
    return [
        f"Agent: {plan.agent}",
        "Arms:",
        *arm_lines,
        f"Tools: {', '.join(profile.enabled_tools) or NO_TOOLS_TEXT}",
        f"Withheld tools: {', '.join(profile.withheld_tools) or NONE_TEXT}",
        f"Grader: {_render_grader(plan)}",
        f"Fixtures: {', '.join(fixture.stem for fixture in plan.fixtures)}",
        f"Trials per arm per fixture: {settings.trials.count} ({settings.trials.reason})",
        f"Trial timeout: {settings.trial_timeout_seconds:g} s",
        _render_estimate(run_estimate),
    ]


def _render_grader(plan: RunPlan) -> str:
    grading = plan.grading
    text = grading.kind.value
    if grading.judge is not None:
        text += f" (judge {grading.judge.model}, effort {grading.judge.effort})"
    if grading.sandbox:
        text += "; write tools enabled in the trial's temp copy"
    return text


def _render_estimate(run_estimate: RunEstimate) -> str:
    per_arm = ", ".join(
        f"{label} {format_usd(cost_usd)}" for label, cost_usd in run_estimate.by_arm
    )
    judge = (
        f", rubric judge {format_usd(run_estimate.judge_usd)}"
        if run_estimate.judge_usd
        else ""
    )
    return (
        "Estimate (rough; real cost can be several times off, high or low): "
        f"{per_arm}{judge}, total {format_usd(run_estimate.estimated_total_usd)}"
    )
