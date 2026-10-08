"""The data a run is made of: its identity, trial counts, settings, progress and result.

Plain types shared by planning, execution, the artifact and the reports, so none of
those has to import another to name them.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .arm import Arm
from .fixtures import FixtureKind
from .outcome import TrialResult
from .run_status import AbortReason, RunStatus

RUN_ID_TIME_FORMAT = "%Y%m%dT%H%M%SZ"
RUN_ID_RANDOM_BITS = 16
RUN_ID_RANDOM_HEX_DIGITS = RUN_ID_RANDOM_BITS // 4


@dataclass(frozen=True)
class RunMetadata:
    """Run-level fields. `created` must be a timezone-aware UTC datetime."""

    run_id: str
    created: datetime
    git_sha: str | None
    agent: str
    knowledge_dir: str


def make_run_id(now: datetime, agent: str, model: str, effort: str, rng) -> str:
    """Return `<UTC time>-<agent>-<model>-<effort>-<4 random hex>`; `rng` needs `getrandbits`."""
    stamp = now.strftime(RUN_ID_TIME_FORMAT)
    suffix = f"{rng.getrandbits(RUN_ID_RANDOM_BITS):0{RUN_ID_RANDOM_HEX_DIGITS}x}"
    return f"{stamp}-{agent}-{model}-{effort}-{suffix}"


# Exact agent names: `security-reviewer` is not in the set.
HIGH_STAKES_AGENTS = frozenset(
    {"security-review", "correctness-review", "architect", "security-engineer"}
)
DEFAULT_TRIALS = 5
HIGH_STAKES_TRIALS = 10
TRIALS_DEFAULT_REASON = "default"
TRIALS_HIGH_STAKES_REASON = "high-stakes default"
TRIALS_FLAG_REASON = "--trials"


@dataclass(frozen=True)
class TrialCount:
    """Trials per arm per fixture, and why that number was chosen."""

    count: int
    reason: str


def resolve_trials(flag_value: int | None, agent: str) -> TrialCount:
    """Return `--trials` if given, else the high-stakes or the general default."""
    if flag_value is not None:
        return TrialCount(flag_value, TRIALS_FLAG_REASON)
    if agent in HIGH_STAKES_AGENTS:
        return TrialCount(HIGH_STAKES_TRIALS, TRIALS_HIGH_STAKES_REASON)
    return TrialCount(DEFAULT_TRIALS, TRIALS_DEFAULT_REASON)


@dataclass(frozen=True)
class TrialSettings:
    """How each trial runs, apart from what the plan fixes."""

    trial_count: TrialCount
    trial_timeout_seconds: float
    claude_bin: str
    expected_dir: Path


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
            for fixture in arm_run.fixture_trials
        )
