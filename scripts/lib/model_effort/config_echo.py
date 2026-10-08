"""Render the resolved run configuration and cost estimate as the lines printed before any trial."""

from __future__ import annotations

from dataclasses import dataclass

from .estimate import RunEstimate
from .plan import RunPlan

NO_TOOLS_TEXT = "no tools enabled"
NONE_TEXT = "none"


@dataclass(frozen=True)
class TrialCount:
    """Trials per arm per fixture, and why that number was chosen."""

    count: int
    reason: str


def format_usd(amount: float) -> str:
    """Four decimals, so a sub-cent haiku estimate does not read as $0.00."""
    return f"${amount:.4f}"


def render_config(
    plan: RunPlan,
    trials: TrialCount,
    trial_timeout: float,
    estimate: RunEstimate,
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
        f"Trials per arm per fixture: {trials.count} ({trials.reason})",
        f"Trial timeout: {trial_timeout:g} s",
        _render_estimate(estimate),
    ]


def _render_estimate(estimate: RunEstimate) -> str:
    per_arm = ", ".join(
        f"{label} {format_usd(cost)}" for label, cost in estimate.by_arm
    )
    return (
        "Estimate (rough; real cost may be higher): "
        f"{per_arm}, total {format_usd(estimate.total_usd)}"
    )
