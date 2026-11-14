"""Whether a run's graded trials are enough to move a tier."""

from __future__ import annotations

from collections.abc import Sequence
from itertools import product

from .grader_config import AgentGrading
from .outcome import GRADED_OUTCOMES
from .run_types import ArmRun
from .trial_count import can_justify_tier_change


def tier_change_eligible(
    arm_runs: Sequence[ArmRun], grading: AgentGrading, fixture_stems: Sequence[str] = ()
) -> bool:
    """Whether the graded trials meet the grader's per-arm, per-fixture floor.

    Only a trial whose answer was graded (`pass` or `graded_fail`) counts: a
    timeout, CLI error, tool violation, parse failure or judge error says
    nothing about the answer. The fewest graded trials of any arm on any planned
    fixture (`fixture_stems`, or every fixture a trial completed on) must be at
    least one and meet the grader's floor (`can_justify_tier_change`).
    """
    completed = {
        (arm_run.arm.label, fixture.stem): sum(
            1 for result in fixture.results if result.outcome in GRADED_OUTCOMES
        )
        for arm_run in arm_runs
        for fixture in arm_run.fixture_trials
    }
    stems = list(fixture_stems) or sorted({stem for _, stem in completed})
    labels = [arm_run.arm.label for arm_run in arm_runs]
    fewest = min(
        (completed.get(key, 0) for key in product(labels, stems)), default=0
    )
    return fewest > 0 and can_justify_tier_change(grading.kind, fewest)
