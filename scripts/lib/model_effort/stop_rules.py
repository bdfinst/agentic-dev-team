"""Decide, after each completed trial, whether the run must stop.

Pure: the caller supplies the history, so the rules can be tested without a run.
An operator interrupt is not decided here; it arrives as an exception.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from .artifact import AbortReason
from .outcome import INFRA_OUTCOMES, Outcome

# Consecutive infrastructure outcomes in one arm that mark the failure as systemic.
CONSECUTIVE_INFRA_FAILURE_LIMIT = 3


def check_stop(
    outcomes_by_arm: Mapping[str, Sequence[Outcome]],
    cumulative_cost: float,
    max_cost: float | None,
) -> AbortReason | None:
    """Return why the run must stop now, or `None` to start the next trial.

    `outcomes_by_arm` maps each arm label to that arm's outcomes in run order,
    across fixtures. Spend wins when both rules apply, because it is the one an
    operator set on purpose.
    """
    if max_cost is not None and cumulative_cost > max_cost:
        return AbortReason.MAX_COST
    if any(_is_systemic_failure(history) for history in outcomes_by_arm.values()):
        return AbortReason.INFRA_FAILURE
    return None


def _is_systemic_failure(history: Sequence[Outcome]) -> bool:
    """An arm that never got a first answer, or kept failing the same way."""
    if not history:
        return False
    if history[0] in INFRA_OUTCOMES:
        return True
    recent = history[-CONSECUTIVE_INFRA_FAILURE_LIMIT:]
    return len(recent) == CONSECUTIVE_INFRA_FAILURE_LIMIT and all(
        outcome in INFRA_OUTCOMES for outcome in recent
    )
