"""Run a planned set of trials: both arms alternate trial by trial on each fixture.

Alternation means a broken candidate fails on its first trial instead of after
the whole baseline arm has been paid for.

Requires `scripts/` and `plugins/dev-team/hooks/lib/` on sys.path.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from . import runner, stop_rules, transcript
from .arm import Arm
from .artifact import AbortReason, ArmRun, FixtureTrials
from .fixtures import ResolvedFixture
from .grading import grade_trial
from .outcome import Grader, Outcome, TrialResult, resolve_outcome
from .plan import RunPlan


@dataclass(frozen=True)
class TrialSettings:
    """How each trial runs, apart from what the plan fixes."""

    trials: int
    trial_timeout: float
    claude_bin: str
    expected_dir: Path


@dataclass(frozen=True)
class TrialProgress:
    """One completed trial and where it sits in the run. Numbers are 1-based."""

    arm: str
    fixture_number: int
    fixture_count: int
    stem: str
    trial_number: int
    trial_count: int
    result: TrialResult


@dataclass(frozen=True)
class RunResult:
    """What a run produced. `abort_reason` is `None` when every planned trial ran.

    Arms list only completed trials, and omit a fixture the arm never completed
    a trial for. An interrupted run drops the trial in flight.
    """

    arm_runs: list[ArmRun]
    abort_reason: AbortReason | None
    # The trial whose completion ended the run; `None` after an interrupt, which
    # lands between trials or mid-trial rather than on a completed one.
    stopping_trial: TrialProgress | None

    @property
    def completed_trials(self) -> int:
        return sum(
            len(fixture.results)
            for arm_run in self.arm_runs
            for fixture in arm_run.fixtures
        )


@dataclass(frozen=True)
class _TrialSlot:
    arm: Arm
    fixture: ResolvedFixture
    fixture_number: int
    trial_number: int


class _Ledger:
    """Completed trials so far, in the shapes the stop rules and the artifact need."""

    def __init__(self, plan: RunPlan) -> None:
        self._plan = plan
        self._results: dict[tuple[str, str], list[TrialResult]] = {}
        self._outcomes_by_arm: dict[str, list[Outcome]] = {
            arm.label: [] for arm in plan.arms
        }
        self._costs: list[float] = []

    def record(self, slot: _TrialSlot, result: TrialResult) -> None:
        key = (slot.arm.label, slot.fixture.stem)
        self._results.setdefault(key, []).append(result)
        self._outcomes_by_arm[slot.arm.label].append(result.outcome)
        self._costs.append(result.cost_usd)

    @property
    def outcomes_by_arm(self) -> Mapping[str, list[Outcome]]:
        return self._outcomes_by_arm

    @property
    def cumulative_cost(self) -> float:
        return math.fsum(self._costs)

    def arm_runs(
        self, trials_per_fixture: int, estimated_costs: Mapping[str, float]
    ) -> list[ArmRun]:
        return [
            ArmRun(
                arm=arm,
                trials_per_fixture=trials_per_fixture,
                estimated_cost_usd=estimated_costs.get(arm.label),
                fixtures=[
                    FixtureTrials(
                        stem=fixture.stem,
                        kind=fixture.kind,
                        expected_clean=fixture.expected_clean,
                        results=self._results[(arm.label, fixture.stem)],
                    )
                    for fixture in self._plan.fixtures
                    if (arm.label, fixture.stem) in self._results
                ],
            )
            for arm in self._plan.arms
        ]


def run_trials(
    plan: RunPlan,
    settings: TrialSettings,
    estimated_costs: Mapping[str, float] | None = None,
    *,
    max_cost: float | None = None,
    on_trial: Callable[[TrialProgress], None] | None = None,
) -> RunResult:
    """Run trials in order until the plan is done, a stop rule fires or the operator interrupts.

    `estimated_costs` maps arm label to its pre-run estimate, recorded on the arm.
    `on_trial` is called after each completed trial, before the stop rules run.
    """
    ledger = _Ledger(plan)
    abort_reason: AbortReason | None = None
    stopping_trial: TrialProgress | None = None
    try:
        for slot in _trial_slots(plan, settings):
            result = _run_trial(slot, plan, settings)
            ledger.record(slot, result)
            progress = _progress(slot, plan, settings, result)
            if on_trial is not None:
                on_trial(progress)
            abort_reason = stop_rules.check_stop(
                ledger.outcomes_by_arm, ledger.cumulative_cost, max_cost
            )
            if abort_reason is not None:
                stopping_trial = progress
                break
    except KeyboardInterrupt:
        abort_reason = AbortReason.INTERRUPT
    return RunResult(
        arm_runs=ledger.arm_runs(settings.trials, estimated_costs or {}),
        abort_reason=abort_reason,
        stopping_trial=stopping_trial,
    )


def _trial_slots(plan: RunPlan, settings: TrialSettings) -> Iterator[_TrialSlot]:
    """Every planned trial in run order: arms alternate, round by round, fixture by fixture."""
    for fixture_number, fixture in enumerate(plan.fixtures, start=1):
        for trial_number in range(1, settings.trials + 1):
            for arm in plan.arms:
                yield _TrialSlot(arm, fixture, fixture_number, trial_number)


def _progress(
    slot: _TrialSlot, plan: RunPlan, settings: TrialSettings, result: TrialResult
) -> TrialProgress:
    return TrialProgress(
        arm=slot.arm.label,
        fixture_number=slot.fixture_number,
        fixture_count=len(plan.fixtures),
        stem=slot.fixture.stem,
        trial_number=slot.trial_number,
        trial_count=settings.trials,
        result=result,
    )


def _run_trial(slot: _TrialSlot, plan: RunPlan, settings: TrialSettings) -> TrialResult:
    grader = partial(
        grade_trial, plan.agent, slot.fixture.stem, expected_dir=settings.expected_dir
    )
    config = _trial_config(slot.arm, plan, settings)
    return _run_and_grade_trial(slot.fixture, config, settings.trial_timeout, grader)


def _trial_config(
    arm: Arm, plan: RunPlan, settings: TrialSettings
) -> runner.TrialConfig:
    return runner.TrialConfig(
        arm=arm, system_prompt=plan.system_prompt, claude_bin=settings.claude_bin
    )


def _run_and_grade_trial(
    fixture: ResolvedFixture,
    config: runner.TrialConfig,
    trial_timeout: float,
    grader: Grader,
) -> TrialResult:
    record = runner.run_trial(fixture.path, config, trial_timeout)
    parsed = transcript.parse_stream(record.stdout)
    return resolve_outcome(record, parsed, config.arm.profile.enabled_tools, grader)
