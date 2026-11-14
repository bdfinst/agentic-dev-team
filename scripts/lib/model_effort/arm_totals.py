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
from .outcome import Outcome, TrialResult
from .run_types import ArmRun, FixtureTrials


@dataclass(frozen=True)
class ArmTotals:
    """What one arm's trials added up to.

    `outcome_counts` has every `Outcome`, zeros included, in precedence order.
    `clean_fixture_false_positives` counts `graded_fail` trials on fixtures that
    expect no findings; a timeout or CLI error says nothing about the answer. On
    a fixture the agent should skip, a failed trial counts only when it reported
    issues: a 0-issue `pass` instead of `skip` is a wrong status, not a finding.
    `actual_cost_usd` sums the reported costs, so it is a lower bound when any
    trial reported none; `unreported_trials_estimate_usd` is what the spend limit
    charged for those trials in their place, and for rubric judgements that
    reported no cost. `judge_cost_usd` sums what the judge reported, failed
    judgements included; `estimated_judge_cost_usd` is the arm's share of the
    pre-run judge estimate, so the arms' shares add up to the echoed figure.
    """

    label: str
    outcome_counts: Mapping[Outcome, int]
    clean_fixture_false_positives: int
    actual_cost_usd: float
    unreported_trials_estimate_usd: float
    estimated_cost_usd: float
    # What the rubric judge reported for this arm's trials; 0.0 when no judge ran.
    judge_cost_usd: float = 0.0
    # This arm's share of the pre-run rubric judge estimate; 0.0 when no judge runs.
    estimated_judge_cost_usd: float = 0.0


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
            for result in fixture.results
            if _is_clean_fixture_false_positive(fixture, result)
        ),
        actual_cost_usd=total_cost_usd(
            result.reported_cost_usd for result in arm_run.results
        ),
        unreported_trials_estimate_usd=total_cost_usd(
            [
                *(
                    run_estimate.charged_usd(label, result)
                    for result in arm_run.results
                    if not result.cost_reported
                ),
                *(
                    run_estimate.charged_judge_usd(result)
                    for result in arm_run.results
                    if result.judged and result.judge_cost_usd is None
                ),
            ]
        ),
        estimated_cost_usd=run_estimate.cost_usd_for_arm(label),
        judge_cost_usd=total_cost_usd(
            result.judge_cost_usd or 0.0 for result in arm_run.results
        ),
        estimated_judge_cost_usd=run_estimate.judge_usd / run_estimate.arm_count,
    )


def _is_clean_fixture_false_positive(
    fixture: FixtureTrials, result: TrialResult
) -> bool:
    if not fixture.expected_clean or result.outcome != Outcome.GRADED_FAIL:
        return False
    if fixture.expected_skip:
        return (result.reported_issue_count or 0) > 0
    return True
