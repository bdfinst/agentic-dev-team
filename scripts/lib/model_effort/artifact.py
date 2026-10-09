"""Assemble the run artifact: pure data in, JSON-ready dict out.

No clock, git, random or file access happens here; the CLI supplies those and
the artifact store does the write. The schema is the one the A/B harness
contract defines.
"""

from __future__ import annotations

from collections.abc import Sequence

from .arm import BASELINE_LABEL
from .arm_totals import ArmTotals, compute_arm_totals
from .estimate import RunEstimate
from .outcome import TrialResult
from .run_status import AbortReason, RunStatus
from .run_types import ArmRun, FixtureTrials, RunMetadata
from .tools import ToolProfile

FIDELITY = "read-only-profile"
GRADER = "expected-findings"

CREATED_TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def build_artifact(
    metadata: RunMetadata,
    arm_runs: Sequence[ArmRun],
    run_estimate: RunEstimate,
    profile: ToolProfile,
    abort_reason: AbortReason | None,
) -> dict:
    """Build the artifact dict, joining each arm's results with its pre-run estimate.

    The status follows from `abort_reason`: incomplete exactly when it is set.

    Both arms record the plan's one tool profile.

    The run-level `session_config` is the baseline arm's, because the baseline
    is the reference configuration; each arm also carries its own.
    """
    arms = [_arm_dict(arm_run, run_estimate, profile) for arm_run in arm_runs]
    return {
        "run_id": metadata.run_id,
        "status": RunStatus.of(abort_reason).value,
        "abort_reason": abort_reason.value if abort_reason else None,
        "created": metadata.created.strftime(CREATED_TIME_FORMAT),
        "git_sha": metadata.git_sha,
        "agent": metadata.agent,
        "grader": GRADER,
        "fidelity": FIDELITY,
        "knowledge_dir": metadata.knowledge_dir,
        "session_config": _baseline_session_config(arms),
        "arms": arms,
    }


def _baseline_session_config(arms: Sequence[dict]) -> dict | None:
    for arm in arms:
        if arm["label"] == BASELINE_LABEL:
            return arm["session_config"]
    return None


def _arm_dict(arm_run: ArmRun, run_estimate: RunEstimate, profile: ToolProfile) -> dict:
    arm = arm_run.arm
    totals = compute_arm_totals(arm_run, run_estimate)
    model_id, model_id_note = _resolve_model_id(arm_run)
    return {
        "label": arm.label,
        "model": arm.model,
        "model_id": model_id,
        "model_id_note": model_id_note,
        "effort": arm.effort,
        "tools_enabled": list(profile.enabled_tools),
        "tools_withheld": list(profile.withheld_tools),
        "trials_per_fixture": arm_run.trials_per_fixture,
        "estimated_cost_usd": totals.estimated_cost_usd,
        "session_config": _first_session_config(arm_run),
        "fixtures": [_fixture_dict(fixture) for fixture in arm_run.fixture_trials],
        "totals": _totals_dict(totals),
    }


def _fixture_dict(fixture: FixtureTrials) -> dict:
    return {
        "stem": fixture.stem,
        "kind": fixture.kind.value,
        "expected_clean": fixture.expected_clean,
        "trials": [_trial_dict(result) for result in fixture.results],
    }


def _trial_dict(result: TrialResult) -> dict:
    return {
        "outcome": result.outcome.value,
        "cost_usd": result.reported_cost_usd,
        "cost_reported": result.cost_reported,
        "grader_messages": list(result.grader_messages),
        "error": result.error,
    }


def _totals_dict(totals: ArmTotals) -> dict:
    return {
        **{outcome.value: count for outcome, count in totals.outcome_counts.items()},
        "clean_fixture_false_positives": totals.clean_fixture_false_positives,
        "actual_cost_usd": totals.actual_cost_usd,
        "unreported_trials_estimate_usd": totals.unreported_trials_estimate_usd,
    }


def _first_session_config(arm_run: ArmRun) -> dict | None:
    """The arm's session config from its first trial whose stream had an init event."""
    for result in arm_run.results:
        if result.session_config is not None:
            return result.session_config
    return None


def _resolve_model_id(arm_run: ArmRun) -> tuple[str | None, str | None]:
    """One model ID if every trial that reported one agrees; otherwise None and a note."""
    results = arm_run.results
    reported = sorted({r.model_id for r in results if r.model_id is not None})
    if len(reported) == 1:
        return reported[0], None
    if len(reported) > 1:
        return None, f"trials reported several model IDs: {', '.join(reported)}"
    notes = [r.model_id_note for r in results if r.model_id_note]
    return None, notes[0] if notes else "no trial reported a model ID"
