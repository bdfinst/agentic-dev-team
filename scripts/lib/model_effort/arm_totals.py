"""One arm's totals: the single place the counting and cost rules live.

The artifact serializes `ArmTotals` and the console summary reads the same type,
so what the operator sees cannot disagree with what was written.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass

from .cost import total_cost_usd
from .estimate import RunEstimate
from .outcome import Outcome
from .run_types import ArmRun


@dataclass(frozen=True)
class ArmTotals:
    """What one arm's trials added up to.

    `outcome_counts` has every `Outcome`, zeros included, in precedence order.
    `clean_fixture_false_positives` counts `graded_fail` trials on fixtures that
    expect no findings; a timeout or CLI error says nothing about the answer.
    `actual_cost_usd` sums the reported costs, so it is a lower bound when any
    trial reported none; `unreported_trials_estimate_usd` is what the spend limit
    charged for those trials in their place.
    """

    label: str
    outcome_counts: Mapping[Outcome, int]
    clean_fixture_false_positives: int
    actual_cost_usd: float
    unreported_trials_estimate_usd: float
    estimated_cost_usd: float


def compute_arm_totals(arm_run: ArmRun, run_estimate: RunEstimate) -> ArmTotals:
    """Total one arm's completed trials against its pre-run estimate."""
    label = arm_run.arm.label
    counts = Counter(result.outcome for result in arm_run.results)
    return ArmTotals(
        label=label,
        outcome_counts={outcome: counts[outcome] for outcome in Outcome},
        clean_fixture_false_positives=sum(
            1
            for fixture in arm_run.fixture_trials
            if fixture.expected_clean
            for result in fixture.results
            if result.outcome == Outcome.GRADED_FAIL
        ),
        actual_cost_usd=total_cost_usd(
            result.reported_cost_usd for result in arm_run.results
        ),
        unreported_trials_estimate_usd=total_cost_usd(
            run_estimate.charged_usd(label, result)
            for result in arm_run.results
            if not result.cost_reported
        ),
        estimated_cost_usd=run_estimate.cost_usd_for_arm(label),
    )
