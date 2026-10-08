"""Render the resolved run configuration and cost estimate as the lines printed before any trial."""

from __future__ import annotations

from .estimate import RunEstimate
from .execution import TrialSettings
from .formatting import format_usd
from .plan import RunPlan

NO_TOOLS_TEXT = "no tools enabled"
NONE_TEXT = "none"


def render_config(
    plan: RunPlan, settings: TrialSettings, run_estimate: RunEstimate
) -> list[str]:
    # Both arms share one tool profile (plan_run builds them from the same agent).
    profile = plan.arms[0].profile
    arm_lines = [
        f"  {arm.label}: model {arm.model}, effort {arm.effort}" for arm in plan.arms
    ]
    return [
        f"Agent: {plan.agent}",
        "Arms:",
        *arm_lines,
        f"Tools: {', '.join(profile.enabled_tools) or NO_TOOLS_TEXT}",
        f"Withheld tools: {', '.join(profile.withheld_tools) or NONE_TEXT}",
        f"Fixtures: {', '.join(fixture.stem for fixture in plan.fixtures)}",
        f"Trials per arm per fixture: {settings.trials.count} ({settings.trials.reason})",
        f"Trial timeout: {settings.trial_timeout:g} s",
        _render_estimate(run_estimate),
    ]


def _render_estimate(run_estimate: RunEstimate) -> str:
    per_arm = ", ".join(
        f"{label} {format_usd(cost_usd)}" for label, cost_usd in run_estimate.by_arm
    )
    return (
        "Estimate (rough; real cost may be higher): "
        f"{per_arm}, total {format_usd(run_estimate.total_usd)}"
    )
