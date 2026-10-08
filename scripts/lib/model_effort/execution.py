"""Run a planned set of trials: both arms alternate trial by trial on each fixture.

Alternation means a broken candidate fails on its first trial instead of after
the whole baseline arm has been paid for.

Requires `scripts/` and `plugins/dev-team/hooks/lib/` on sys.path.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from . import runner, stop_rules, transcript
from .arm import Arm
from .artifact import ArmRun, FixtureTrials
from .cost import total_cost_usd
from .estimate import RunEstimate
from .fixtures import ResolvedFixture
from .grading import grade_trial
from .outcome import MAX_MESSAGE_CHARS, Grader, Outcome, TrialResult, resolve_outcome
from .plan import RunPlan
from .run_status import AbortReason, RunStatus
from .stop_rules import SpendLimit

# Runs one trial of a config against a fixture; `runner.run_trial` in production.
TrialRunner = Callable[[Path, runner.TrialConfig, float], runner.RunRecord]


@dataclass(frozen=True)
class TrialCount:
    """Trials per arm per fixture, and why that number was chosen."""

    count: int
    reason: str


@dataclass(frozen=True)
class TrialSettings:
    """How each trial runs, apart from what the plan fixes."""

    trials: TrialCount
    trial_timeout: float
    claude_bin: str
    expected_dir: Path


@dataclass(frozen=True)
class TrialProgress:
    """One completed trial and where it sits in the run. Numbers are 1-based."""

    arm_label: str
    fixture_number: int
    fixture_count: int
    fixture_stem: str
    trial_number: int
    trial_count: int
    result: TrialResult


@dataclass(frozen=True)
class RunResult:
    """What a run produced. `abort_reason` is `None` when every planned trial ran.

    Arms list only completed trials, and omit a fixture the arm never completed
    a trial for. An interrupted run drops the trial in flight, but still counts
    it in `started_trials`.
    """

    arm_runs: list[ArmRun]
    abort_reason: AbortReason | None
    started_trials: int
    # The trial whose completion ended the run; `None` after an interrupt, which
    # lands between trials or mid-trial rather than on a completed one.
    stopping_trial: TrialProgress | None
    # The error type and message that ended the run, for `harness-error` only.
    harness_error: str | None = None

    @property
    def status(self) -> RunStatus:
        return RunStatus.of(self.abort_reason)

    @property
    def is_complete(self) -> bool:
        return self.status is RunStatus.COMPLETE

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

    def __init__(self, plan: RunPlan, run_estimate: RunEstimate) -> None:
        self._plan = plan
        self._run_estimate = run_estimate
        self._results: dict[tuple[str, str], list[TrialResult]] = {}
        self._outcomes_by_arm: dict[str, list[Outcome]] = {
            arm.label: [] for arm in plan.arms
        }
        self._costs_usd: list[float] = []

    def record(self, slot: _TrialSlot, result: TrialResult) -> None:
        key = (slot.arm.label, slot.fixture.stem)
        self._results.setdefault(key, []).append(result)
        self._outcomes_by_arm[slot.arm.label].append(result.outcome)
        self._costs_usd.append(self._cost_charged_usd(slot, result))

    def _cost_charged_usd(self, slot: _TrialSlot, result: TrialResult) -> float:
        """The reported cost, or the arm's per-trial estimate when the trial reported none."""
        if result.cost_reported:
            return result.cost_usd
        return self._run_estimate.per_trial_usd(slot.arm.label)

    @property
    def outcomes_by_arm(self) -> Mapping[str, list[Outcome]]:
        return self._outcomes_by_arm

    @property
    def cumulative_cost_usd(self) -> float:
        return total_cost_usd(self._costs_usd)

    def arm_runs(self, trials_per_fixture: int) -> list[ArmRun]:
        return [
            ArmRun(
                arm=arm,
                trials_per_fixture=trials_per_fixture,
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
    run_estimate: RunEstimate,
    *,
    run_trial: TrialRunner,
    spend_limit: SpendLimit | None = None,
    on_trial: Callable[[TrialProgress], None] | None = None,
) -> RunResult:
    """Run trials in order until the plan is done, a stop rule fires or the run is cut short.

    `run_estimate` prices a trial that reports no cost, so the spend limit still sees it.
    `on_trial` is called after each completed trial, before the stop rules run.
    A stop that fires on the last planned trial skips nothing, so it does not end the
    run early. An operator interrupt or an unexpected error keeps the completed trials.
    """
    ledger = _Ledger(plan, run_estimate)
    slots = list(_trial_slots(plan, settings))
    started_trials = 0
    abort_reason: AbortReason | None = None
    stopping_trial: TrialProgress | None = None
    harness_error: str | None = None
    try:
        for index, slot in enumerate(slots):
            started_trials += 1
            result = _run_slot(slot, plan, settings, run_trial)
            ledger.record(slot, result)
            progress = _progress(slot, plan, settings, result)
            if on_trial is not None:
                on_trial(progress)
            stop_reason = stop_rules.check_stop(
                ledger.outcomes_by_arm, ledger.cumulative_cost_usd, spend_limit
            )
            if stop_reason is not None and index < len(slots) - 1:
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


def _trial_slots(plan: RunPlan, settings: TrialSettings) -> Iterator[_TrialSlot]:
    """Every planned trial in run order: arms alternate, round by round, fixture by fixture."""
    for fixture_number, fixture in enumerate(plan.fixtures, start=1):
        for trial_number in range(1, settings.trials.count + 1):
            for arm in plan.arms:
                yield _TrialSlot(arm, fixture, fixture_number, trial_number)


def _progress(
    slot: _TrialSlot, plan: RunPlan, settings: TrialSettings, result: TrialResult
) -> TrialProgress:
    return TrialProgress(
        arm_label=slot.arm.label,
        fixture_number=slot.fixture_number,
        fixture_count=len(plan.fixtures),
        fixture_stem=slot.fixture.stem,
        trial_number=slot.trial_number,
        trial_count=settings.trials.count,
        result=result,
    )


def _run_slot(
    slot: _TrialSlot, plan: RunPlan, settings: TrialSettings, run_trial: TrialRunner
) -> TrialResult:
    grader = partial(
        grade_trial, plan.agent, slot.fixture.stem, expected_dir=settings.expected_dir
    )
    config = _trial_config(slot.arm, plan, settings)
    return _run_and_grade_trial(
        slot.fixture, config, settings.trial_timeout, grader, run_trial
    )


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
    run_trial: TrialRunner,
) -> TrialResult:
    record = run_trial(fixture.path, config, trial_timeout)
    parsed = transcript.parse_stream(record.stdout)
    return resolve_outcome(record, parsed, config.arm.profile.enabled_tools, grader)
