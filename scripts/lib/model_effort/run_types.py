"""The data a run is made of: its identity, settings, progress and result.

Plain types shared by planning, execution, the artifact and the reports, so none of
those has to import another to name them.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from .arm import Arm
from .fixtures import FixtureKind
from .outcome import TrialResult
from .run_status import AbortReason, RunStatus
from .trial_count import TrialCount


@dataclass(frozen=True)
class RunMetadata:
    """Run-level fields. `created` must be a timezone-aware UTC datetime."""

    run_id: str
    created: datetime
    git_sha: str | None
    agent: str
    knowledge_dir: str


@dataclass(frozen=True)
class TrialSettings:
    """How each trial runs, apart from what the plan fixes (the plan's snapshot owns the input paths)."""

    trials: TrialCount
    trial_timeout_seconds: float
    claude_bin: str


@dataclass(frozen=True)
class FixtureTrials:
    stem: str
    kind: FixtureKind
    expected_clean: bool
    results: Sequence[TrialResult]


@dataclass(frozen=True)
class ArmRun:
    arm: Arm
    trials_per_fixture: int
    fixture_trials: Sequence[FixtureTrials]

    @property
    def results(self) -> list[TrialResult]:
        """Every completed trial of the arm, fixture by fixture."""
        return [result for fixture in self.fixture_trials for result in fixture.results]


@dataclass(frozen=True)
class TrialProgress:
    """One completed trial and where it sits in the run. Numbers are 1-based."""

    arm_label: str
    fixture_number: int
    fixture_count: int
    fixture_stem: str
    trial_number: int
    trials_per_fixture: int
    result: TrialResult


@dataclass(frozen=True)
class RunResult:
    """What a run produced. `abort_reason` is `None` when every planned trial ran.

    Arms list only completed trials, and omit a fixture the arm never completed
    a trial for. An interrupt that lands in a trial's process drops that trial, but
    still counts it in `started_trials`; one found between trials drops nothing.
    """

    arm_runs: list[ArmRun]
    abort_reason: AbortReason | None
    started_trials: int
    # The trial whose completion ended the run; `None` after an interrupt, which
    # is found between trials or in a trial's process, not on a completed trial.
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
            for fixture in arm_run.fixture_trials
        )
