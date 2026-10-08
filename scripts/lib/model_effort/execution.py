"""Run a planned set of trials: both arms alternate trial by trial on each fixture.

Alternation means a broken candidate fails on its first trial instead of after
the whole baseline arm has been paid for.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from . import interrupts, invocation, stop_rules, transcript
from .arm import Arm
from .cost import total_cost_usd
from .estimate import RunEstimate
from .fixtures import ResolvedFixture
from .grading import grade_trial
from .outcome import MAX_MESSAGE_CHARS, Outcome, TrialResult, resolve_outcome
from .plan import RunPlan
from .process_record import TrialProcessRecord
from .run_status import AbortReason
from .run_types import (
    ArmRun,
    FixtureTrials,
    RunResult,
    TrialProgress,
    TrialSettings,
)
from .stop_rules import SpendLimit

# Runs one trial of a config against a fixture; `runner.run_trial` in production.
TrialRunner = Callable[[Path, invocation.TrialConfig, float], TrialProcessRecord]


@dataclass(frozen=True)
class _TrialSlot:
    arm: Arm
    fixture: ResolvedFixture
    fixture_number: int
    trial_number: int


class _Ledger:
    """Completed trials so far, in the shapes the stop rules and the artifact need."""

    def __init__(self, plan: RunPlan, run_estimate: RunEstimate) -> None:
        self._plan = plan
        self._run_estimate = run_estimate
        self._results_by_arm_and_fixture: dict[tuple[str, str], list[TrialResult]] = {}
        self._outcomes_by_arm: dict[str, list[Outcome]] = {
            arm.label: [] for arm in plan.arms
        }
        self._charged_usd: list[float] = []

    def record(self, slot: _TrialSlot, result: TrialResult) -> None:
        key = (slot.arm.label, slot.fixture.stem)
        self._results_by_arm_and_fixture.setdefault(key, []).append(result)
        self._outcomes_by_arm[slot.arm.label].append(result.outcome)
        self._charged_usd.append(self._run_estimate.charged_usd(slot.arm.label, result))

    @property
    def outcomes_by_arm(self) -> Mapping[str, list[Outcome]]:
        return self._outcomes_by_arm

    @property
    def cumulative_charged_usd(self) -> float:
        return total_cost_usd(self._charged_usd)

    def arm_runs(self, trials_per_fixture: int) -> list[ArmRun]:
        return [
            ArmRun(
                arm=arm,
                trials_per_fixture=trials_per_fixture,
                fixture_trials=[
                    FixtureTrials(
                        stem=fixture.stem,
                        kind=fixture.kind,
                        expected_clean=fixture.expected_clean,
                        results=self._results_by_arm_and_fixture[
                            (arm.label, fixture.stem)
                        ],
                    )
                    for fixture in self._plan.fixtures
                    if (arm.label, fixture.stem) in self._results_by_arm_and_fixture
                ],
            )
            for arm in self._plan.arms
        ]


def run_trials(
    plan: RunPlan,
    settings: TrialSettings,
    run_estimate: RunEstimate,
    *,
    run_trial: TrialRunner,
    spend_limit: SpendLimit | None = None,
    on_trial: Callable[[TrialProgress], None] | None = None,
) -> RunResult:
    """Run trials in order until the plan is done, a stop rule fires or the run is cut short.

    `run_estimate` prices a trial that reports no cost, so the spend limit still sees it.
    `on_trial` is called after each completed trial, before the stop rules run.
    A stop on the last planned trial skips nothing, so the stop rules ignore it. An
    operator interrupt or an unexpected error keeps the completed trials.

    The caller holds the interrupt signals (see `interrupts`), so a signal never
    drops a trial that finished. One that arrived while a trial was being resolved,
    graded or recorded is found before the next trial starts and ends the run.
    """
    executor = _TrialExecutor(plan, settings, run_trial)
    ledger = _Ledger(plan, run_estimate)
    slots = list(executor.slots())
    started_trials = 0
    abort_reason: AbortReason | None = None
    stopping_trial: TrialProgress | None = None
    harness_error: str | None = None
    try:
        for index, slot in enumerate(slots):
            if interrupts.take_pending():
                abort_reason = AbortReason.INTERRUPT
                break
            started_trials += 1
            result = executor.run(slot)
            ledger.record(slot, result)
            progress = executor.progress(slot, result)
            if on_trial is not None:
                on_trial(progress)
            stop_reason = stop_rules.check_stop(
                ledger.outcomes_by_arm,
                ledger.cumulative_charged_usd,
                spend_limit,
                trials_remaining=len(slots) - index - 1,
            )
            if stop_reason is not None:
                abort_reason = stop_reason
                stopping_trial = progress
                break
    except KeyboardInterrupt:
        abort_reason = AbortReason.INTERRUPT
    except Exception as error:  # noqa: BLE001 - keep the paid trials whatever failed
        abort_reason = AbortReason.HARNESS_ERROR
        harness_error = f"{type(error).__name__}: {error}"[:MAX_MESSAGE_CHARS]
    return RunResult(
        arm_runs=ledger.arm_runs(settings.trials.count),
        abort_reason=abort_reason,
        started_trials=started_trials,
        stopping_trial=stopping_trial,
        harness_error=harness_error,
    )


@dataclass(frozen=True)
class _TrialExecutor:
    """Runs one planned trial at a time; carries the plan, settings and runner once."""

    plan: RunPlan
    settings: TrialSettings
    run_trial: TrialRunner

    def slots(self) -> Iterator[_TrialSlot]:
        """Every planned trial in run order: arms alternate, round by round, fixture by fixture."""
        for fixture_number, fixture in enumerate(self.plan.fixtures, start=1):
            for trial_number in range(1, self.settings.trials.count + 1):
                for arm in self.plan.arms:
                    yield _TrialSlot(arm, fixture, fixture_number, trial_number)

    def run(self, slot: _TrialSlot) -> TrialResult:
        """Run the slot's trial against its fixture, parse the stream and resolve the outcome."""
        config = invocation.TrialConfig(
            arm=slot.arm,
            system_prompt=self.plan.system_prompt,
            profile=self.plan.profile,
            eval_paths=self.settings.eval_paths,
            claude_bin=self.settings.claude_bin,
        )
        record = self.run_trial(
            slot.fixture.path, config, self.settings.trial_timeout_seconds
        )
        grader = partial(
            grade_trial,
            self.plan.agent,
            slot.fixture.stem,
            eval_paths=self.settings.eval_paths,
        )
        return resolve_outcome(
            record,
            transcript.parse_stream(record.stdout),
            self.plan.profile.enabled_tools,
            grader,
        )

    def progress(self, slot: _TrialSlot, result: TrialResult) -> TrialProgress:
        return TrialProgress(
            arm_label=slot.arm.label,
            fixture_number=slot.fixture_number,
            fixture_count=len(self.plan.fixtures),
            fixture_stem=slot.fixture.stem,
            trial_number=slot.trial_number,
            trials_per_fixture=self.settings.trials.count,
            result=result,
        )
