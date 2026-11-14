"""Build trial results, arm runs and estimates directly, without running a trial."""

from __future__ import annotations

import ab_harness_path  # noqa: F401  (puts the harness on sys.path first)
from ab_constants import ARM_ESTIMATE, NOW, RUN_ID, TRIAL_COST
from model_effort import (
    artifact,
    artifact_store,
    estimate,
    outcome,
    process_record,
    run_types,
    tools,
)
from model_effort import fixtures as fixture_resolution
from model_effort.arm import BASELINE_LABEL, CANDIDATE_LABEL, Arm
from model_effort.outcome import Outcome


def trial_result(
    outcome_value: Outcome,
    cost=TRIAL_COST,
    model_id=None,
    note=None,
    session_config=None,
    cost_reported=True,
    issue_count=None,
) -> outcome.TrialResult:
    return outcome.TrialResult(
        outcome=outcome_value,
        reported_cost_usd=cost,
        model_id=model_id,
        model_id_note=note,
        grader_messages=(),
        error=None,
        session_config=session_config,
        cost_reported=cost_reported,
        reported_issue_count=issue_count,
    )


def candidate_arm(label: str = CANDIDATE_LABEL) -> Arm:
    return Arm(label=label, model="haiku", effort="high")


READ_ONLY_PROFILE = tools.ToolProfile(
    enabled_tools=("Read",), withheld_tools=(), refused_tools=()
)


def arm_run_of(
    label: str,
    results: list[outcome.TrialResult],
    expected_clean: bool = False,
    expected_skip: bool = False,
) -> run_types.ArmRun:
    fixture = run_types.FixtureTrials(
        stem="f",
        kind=fixture_resolution.FixtureKind.FILE,
        expected_clean=expected_clean,
        results=results,
        expected_skip=expected_skip,
    )
    return run_types.ArmRun(
        arm=candidate_arm(label), trials_per_fixture=1, fixture_trials=[fixture]
    )


def run_metadata() -> run_types.RunMetadata:
    return run_types.RunMetadata(
        run_id=RUN_ID,
        created=NOW,
        git_sha=None,
        agent="scout",
        knowledge_dir="knowledge",
    )


def flat_run_estimate(total_trials_per_arm: int = 1) -> estimate.RunEstimate:
    return estimate.RunEstimate(
        by_arm=(
            (BASELINE_LABEL, ARM_ESTIMATE * total_trials_per_arm),
            (CANDIDATE_LABEL, ARM_ESTIMATE * total_trials_per_arm),
        ),
        total_trials_per_arm=total_trials_per_arm,
    )


def built_arm(
    results: list[outcome.TrialResult],
    expected_clean: bool = False,
    total_trials_per_arm: int = 1,
) -> dict:
    run = arm_run_of(CANDIDATE_LABEL, results, expected_clean)
    built = artifact.build_artifact(
        run_metadata(),
        [run],
        flat_run_estimate(total_trials_per_arm),
        READ_ONLY_PROFILE,
        None,
    )
    return built["arms"][0]


def _failing_replace(*_args, **_kwargs):
    raise OSError("disk full")


def store_with_failing_replace(monkeypatch) -> None:
    """Make the final move fail while leaving every other os call working."""
    monkeypatch.setattr(artifact_store.os, "replace", _failing_replace)


CLI_FAILURE = {"exit_code": 1, "stdout": "", "stderr": "boom: auth failed"}
CLI_FAILURE_RECORD = process_record.TrialProcessRecord(
    exit_code=1, stdout="", stderr="boom: auth failed", timed_out=False
)
TIMED_OUT_RECORD = process_record.TrialProcessRecord(
    exit_code=None, stdout="", stderr="", timed_out=True
)
