"""Assemble the run artifact: pure data in, JSON-ready dict out.

No clock, git, random or file access happens here; the CLI supplies those and
does the write. The schema is the one the A/B harness contract defines.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from . import outcome
from .outcome import TrialResult

FIDELITY = "read-only-profile"
GRADER = "expected-findings"
STATUS_COMPLETE = "complete"

RUN_ID_TIME_FORMAT = "%Y%m%dT%H%M%SZ"
RUN_ID_RANDOM_BITS = 16
RUN_ID_RANDOM_HEX_DIGITS = RUN_ID_RANDOM_BITS // 4

OUTCOME_NAMES = (
    outcome.OUTCOME_PASS,
    outcome.OUTCOME_GRADED_FAIL,
    outcome.OUTCOME_PARSE_FAILURE,
    outcome.OUTCOME_TOOL_VIOLATION,
    outcome.OUTCOME_CLI_ERROR,
    outcome.OUTCOME_TIMEOUT,
)


@dataclass(frozen=True)
class RunMetadata:
    """Run-level fields. `created` must be a timezone-aware UTC datetime."""

    run_id: str
    created: datetime
    git_sha: str | None
    agent: str
    knowledge_dir: str
    session_config: dict | None = None
    status: str = STATUS_COMPLETE
    abort_reason: str | None = None


@dataclass(frozen=True)
class ArmSpec:
    label: str
    model: str
    effort: str
    tools_enabled: tuple[str, ...]
    tools_withheld: tuple[str, ...]


@dataclass(frozen=True)
class FixtureTrials:
    stem: str
    kind: str
    expected_clean: bool
    results: Sequence[TrialResult]


@dataclass(frozen=True)
class ArmRun:
    spec: ArmSpec
    trials_per_fixture: int
    fixtures: Sequence[FixtureTrials]
    estimated_cost_usd: float | None = None


def make_run_id(now: datetime, agent: str, model: str, effort: str, rng) -> str:
    """Return `<UTC time>-<agent>-<model>-<effort>-<4 random hex>`; `rng` needs `getrandbits`."""
    stamp = now.strftime(RUN_ID_TIME_FORMAT)
    suffix = f"{rng.getrandbits(RUN_ID_RANDOM_BITS):0{RUN_ID_RANDOM_HEX_DIGITS}x}"
    return f"{stamp}-{agent}-{model}-{effort}-{suffix}"


def build_artifact(metadata: RunMetadata, arms: Sequence[ArmRun]) -> dict:
    return {
        "run_id": metadata.run_id,
        "status": metadata.status,
        "abort_reason": metadata.abort_reason,
        "created": metadata.created.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_sha": metadata.git_sha,
        "agent": metadata.agent,
        "grader": GRADER,
        "fidelity": FIDELITY,
        "knowledge_dir": metadata.knowledge_dir,
        "session_config": metadata.session_config,
        "arms": [_arm_dict(arm) for arm in arms],
    }


def _arm_dict(arm: ArmRun) -> dict:
    model_id, model_id_note = _resolve_model_id(arm)
    return {
        "label": arm.spec.label,
        "model": arm.spec.model,
        "model_id": model_id,
        "model_id_note": model_id_note,
        "effort": arm.spec.effort,
        "tools_enabled": list(arm.spec.tools_enabled),
        "tools_withheld": list(arm.spec.tools_withheld),
        "trials": arm.trials_per_fixture,
        "estimated_cost_usd": arm.estimated_cost_usd,
        "fixtures": [_fixture_dict(fixture) for fixture in arm.fixtures],
        "totals": _totals(arm),
    }


def _fixture_dict(fixture: FixtureTrials) -> dict:
    return {
        "stem": fixture.stem,
        "kind": fixture.kind,
        "expected_clean": fixture.expected_clean,
        "trials": [_trial_dict(result) for result in fixture.results],
    }


def _trial_dict(result: TrialResult) -> dict:
    return {
        "outcome": result.outcome,
        "cost_usd": result.cost_usd,
        "grader_messages": list(result.grader_messages),
        "error": result.error,
    }


def _all_results(arm: ArmRun) -> list[TrialResult]:
    return [result for fixture in arm.fixtures for result in fixture.results]


def _totals(arm: ArmRun) -> dict:
    results = _all_results(arm)
    totals: dict = {
        name: sum(1 for result in results if result.outcome == name)
        for name in OUTCOME_NAMES
    }
    totals["clean_fixture_failures"] = sum(
        1
        for fixture in arm.fixtures
        if fixture.expected_clean
        for result in fixture.results
        if result.outcome != outcome.OUTCOME_PASS
    )
    totals["actual_cost_usd"] = math.fsum(result.cost_usd for result in results)
    return totals


def _resolve_model_id(arm: ArmRun) -> tuple[str | None, str | None]:
    """One model ID if every trial that reported one agrees; otherwise None and a note."""
    results = _all_results(arm)
    reported = sorted({r.model_id for r in results if r.model_id is not None})
    if len(reported) == 1:
        return reported[0], None
    if len(reported) > 1:
        return None, f"trials reported several model IDs: {', '.join(reported)}"
    notes = [r.model_id_note for r in results if r.model_id_note]
    return None, notes[0] if notes else "no trial reported a model ID"
