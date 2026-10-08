"""Decide, after each completed trial, whether the run must stop.

Pure: the caller supplies the history, so the rules can be tested without a run.
An operator interrupt is not decided here; it arrives as an exception.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .outcome import INFRA_OUTCOMES, Outcome
from .run_status import AbortReason

# Consecutive infrastructure outcomes in one arm that mark the failure as systemic.
CONSECUTIVE_INFRA_FAILURE_LIMIT = 3


@dataclass(frozen=True)
class SpendLimit:
    """The operator's `--max-cost`. Both checks are strict: spending exactly the limit is allowed."""

    max_cost_usd: float

    def refuses(self, estimate_usd: float) -> bool:
        """True when the pre-run estimate is already above the limit."""
        return estimate_usd > self.max_cost_usd

    def exceeded_by(self, charged_usd: float) -> bool:
        """True when the cost charged so far is above the limit.

        Charged is each trial's reported cost, or its arm's per-trial estimate when it reported none.
        """
        return charged_usd > self.max_cost_usd


def check_stop(
    outcomes_by_arm: Mapping[str, Sequence[Outcome]],
    cumulative_charged_usd: float,
    spend_limit: SpendLimit | None,
    *,
    trials_remaining: int,
) -> AbortReason | None:
    """Return why the run must stop now, or `None` to start the next trial.

    `outcomes_by_arm` maps each arm label to that arm's outcomes in run order,
    across fixtures. Spend wins when both rules apply, because it is the one an
    operator set on purpose. With no trial left, a stop skips nothing, so the run
    stays complete and this returns `None`.
    """
    if trials_remaining == 0:
        return None
    if spend_limit is not None and spend_limit.exceeded_by(cumulative_charged_usd):
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
