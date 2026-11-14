"""The stress matrix's arms: the agent's current tier, one step down and one step up.

A step moves one rung on the model ladder (haiku, sonnet, opus) at the same
effort, or one rung on the effort ladder at the same model. On the model axis a
step that has no model rung left (down from haiku, up from opus) moves effort
instead, so every agent gets both directions where either ladder allows it. A
direction with no rung on either ladder has no arm.
"""

from __future__ import annotations

from enum import StrEnum

from .arm import BASELINE_LABEL, Arm
from .judge_tier import MODEL_TIERS, model_tier

STEP_DOWN_LABEL = "step-down"
STEP_UP_LABEL = "step-up"
# Weakest first, in the agent contract's order.
EFFORT_LADDER = ("low", "medium", "high", "xhigh", "max")
DOWN = -1
UP = 1


class Axis(StrEnum):
    """Which ladder a step moves on first."""

    MODEL = "model"
    EFFORT = "effort"


def stress_arms(model: str, effort: str, axis: Axis) -> tuple[Arm, ...]:
    """The current arm, then the step-down and step-up arms that exist."""
    arms = [Arm(BASELINE_LABEL, model, effort)]
    for label, direction in ((STEP_DOWN_LABEL, DOWN), (STEP_UP_LABEL, UP)):
        stepped = _step(model, effort, direction, axis)
        if stepped is not None:
            arms.append(Arm(label, *stepped))
    return tuple(arms)


def _step(
    model: str, effort: str, direction: int, axis: Axis
) -> tuple[str, str] | None:
    if axis is Axis.MODEL:
        stepped_model = _model_step(model, direction)
        if stepped_model is not None:
            return stepped_model, effort
    stepped_effort = _ladder_step(EFFORT_LADDER, effort, direction)
    return (model, stepped_effort) if stepped_effort is not None else None


def _model_step(model: str, direction: int) -> str | None:
    tier = model_tier(model)
    if tier is None:
        return None
    return _ladder_step(MODEL_TIERS, MODEL_TIERS[tier], direction)


def _ladder_step(ladder: tuple[str, ...], value: str, direction: int) -> str | None:
    if value not in ladder:
        return None
    index = ladder.index(value) + direction
    return ladder[index] if 0 <= index < len(ladder) else None
