"""Run a planned set of trials: both arms alternate trial by trial on each fixture.

Alternation means a broken candidate fails on its first trial instead of after
the whole baseline arm has been paid for.

Requires `scripts/` and `plugins/dev-team/hooks/lib/` on sys.path.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from pathlib import Path

from . import runner, transcript
from .arm import Arm
from .artifact import ArmRun, FixtureTrials
from .fixtures import ResolvedFixture
from .grading import grade_trial
from .outcome import Grader, TrialResult, resolve_outcome
from .plan import RunPlan


@dataclass(frozen=True)
class TrialSettings:
    """How each trial runs, apart from what the plan fixes."""

    trials: int
    trial_timeout: float
    claude_bin: str
    expected_dir: Path


def run_trials(plan: RunPlan, settings: TrialSettings) -> list[ArmRun]:
    """Run every trial in the plan and return one `ArmRun` per planned arm."""
    results_by_fixture = {
        fixture.stem: _run_fixture(fixture, plan, settings) for fixture in plan.fixtures
    }
    return [
        ArmRun(
            arm=arm,
            trials_per_fixture=settings.trials,
            fixtures=[
                FixtureTrials(
                    stem=fixture.stem,
                    kind=fixture.kind,
                    expected_clean=fixture.expected_clean,
                    results=results_by_fixture[fixture.stem][arm.label],
                )
                for fixture in plan.fixtures
            ],
        )
        for arm in plan.arms
    ]


def _run_fixture(
    fixture: ResolvedFixture, plan: RunPlan, settings: TrialSettings
) -> dict[str, list[TrialResult]]:
    """Run `settings.trials` rounds, each round one trial per arm; results keyed by arm label."""
    grader = partial(
        grade_trial, plan.agent, fixture.stem, expected_dir=settings.expected_dir
    )
    results: dict[str, list[TrialResult]] = {arm.label: [] for arm in plan.arms}
    for _ in range(settings.trials):
        for arm in plan.arms:
            config = _trial_config(arm, plan, settings)
            results[arm.label].append(
                _run_and_grade_trial(fixture, config, settings.trial_timeout, grader)
            )
    return results


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
