"""Assemble the run artifact: pure data in, JSON-ready dict out.

No clock, git, random or file access happens here; the CLI supplies those and
the artifact store does the write. The schema is the one the A/B harness
contract defines.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .arm import BASELINE_LABEL, Arm
from .fixtures import FixtureKind
from .outcome import Outcome, TrialResult

FIDELITY = "read-only-profile"
GRADER = "expected-findings"
STATUS_COMPLETE = "complete"
STATUS_INCOMPLETE = "incomplete"

RUN_ID_TIME_FORMAT = "%Y%m%dT%H%M%SZ"
CREATED_TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
RUN_ID_RANDOM_BITS = 16
RUN_ID_RANDOM_HEX_DIGITS = RUN_ID_RANDOM_BITS // 4


class AbortReason(StrEnum):
    """Why a run ended before every planned trial ran."""

    MAX_COST = "max-cost"
    INFRA_FAILURE = "infra-failure"
    INTERRUPT = "interrupt"


@dataclass(frozen=True)
class RunMetadata:
    """Run-level fields. `created` must be a timezone-aware UTC datetime.

    The artifact status is derived: `incomplete` exactly when `abort_reason` is set.
    """

    run_id: str
    created: datetime
    git_sha: str | None
    agent: str
    knowledge_dir: str
    abort_reason: AbortReason | None = None


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
    fixtures: Sequence[FixtureTrials]
    # Filled from the pre-run cost estimate; null until that estimate exists.
    estimated_cost_usd: float | None = None


def make_run_id(now: datetime, agent: str, model: str, effort: str, rng) -> str:
    """Return `<UTC time>-<agent>-<model>-<effort>-<4 random hex>`; `rng` needs `getrandbits`."""
    stamp = now.strftime(RUN_ID_TIME_FORMAT)
    suffix = f"{rng.getrandbits(RUN_ID_RANDOM_BITS):0{RUN_ID_RANDOM_HEX_DIGITS}x}"
    return f"{stamp}-{agent}-{model}-{effort}-{suffix}"


def build_artifact(metadata: RunMetadata, arm_runs: Sequence[ArmRun]) -> dict:
    """Build the artifact dict.

    The run-level `session_config` is the baseline arm's, because the baseline
    is the reference configuration; each arm also carries its own.
    """
    arms = [_arm_dict(arm_run) for arm_run in arm_runs]
    return {
        "run_id": metadata.run_id,
        "status": STATUS_INCOMPLETE if metadata.abort_reason else STATUS_COMPLETE,
        "abort_reason": metadata.abort_reason.value if metadata.abort_reason else None,
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


def _arm_dict(arm_run: ArmRun) -> dict:
    arm = arm_run.arm
    model_id, model_id_note = _resolve_model_id(arm_run)
    return {
        "label": arm.label,
        "model": arm.model,
        "model_id": model_id,
        "model_id_note": model_id_note,
        "effort": arm.effort,
        "tools_enabled": list(arm.profile.enabled_tools),
        "tools_withheld": list(arm.profile.withheld_tools),
        "trials": arm_run.trials_per_fixture,
        "estimated_cost_usd": arm_run.estimated_cost_usd,
        "session_config": _first_session_config(arm_run),
        "fixtures": [_fixture_dict(fixture) for fixture in arm_run.fixtures],
        "totals": _totals(arm_run),
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
        "cost_usd": result.cost_usd,
        "grader_messages": list(result.grader_messages),
        "error": result.error,
    }


def _all_results(arm_run: ArmRun) -> list[TrialResult]:
    return [result for fixture in arm_run.fixtures for result in fixture.results]


def _totals(arm_run: ArmRun) -> dict:
    results = _all_results(arm_run)
    counts = Counter(result.outcome for result in results)
    totals: dict = {outcome.value: counts[outcome] for outcome in Outcome}
    totals["clean_fixture_failures"] = sum(
        1
        for fixture in arm_run.fixtures
        if fixture.expected_clean
        for result in fixture.results
        if result.outcome != Outcome.PASS
    )
    totals["actual_cost_usd"] = math.fsum(result.cost_usd for result in results)
    return totals


def _first_session_config(arm_run: ArmRun) -> dict | None:
    """The arm's session config from its first trial whose stream had an init event."""
    for result in _all_results(arm_run):
        if result.session_config is not None:
            return result.session_config
    return None


def _resolve_model_id(arm_run: ArmRun) -> tuple[str | None, str | None]:
    """One model ID if every trial that reported one agrees; otherwise None and a note."""
    results = _all_results(arm_run)
    reported = sorted({r.model_id for r in results if r.model_id is not None})
    if len(reported) == 1:
        return reported[0], None
    if len(reported) > 1:
        return None, f"trials reported several model IDs: {', '.join(reported)}"
    notes = [r.model_id_note for r in results if r.model_id_note]
    return None, notes[0] if notes else "no trial reported a model ID"
