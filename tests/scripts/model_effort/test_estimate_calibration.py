"""The cost estimate's constants against the costs real runs reported.

Each committed artifact under `evals/model-effort/runs/` records what every arm
cost. Re-estimating each arm with today's constants, agent files, fixtures and
pricing must land at or above what the arm cost, because the estimate feeds the
approval prompt and prices unreported trials toward the spend limit, and must not
land so far above that the estimate stops meaning anything. A rubric-graded arm
gets a looser ceiling: its short answers sit far below the flat per-trial output
allowance. Each arm is priced by
the model ID its artifact recorded, so a tier alias moved to a newer model does
not reprice an old run.
"""

from __future__ import annotations

import json
from pathlib import Path

import ab_harness_path  # noqa: F401  (puts the harness on sys.path first)
import pytest
from model_effort import estimate, external, paths
from model_effort.agent_file import load_agent_file
from model_effort.agent_spec import build_agent_spec
from model_effort.arm import Arm
from model_effort.fixtures import resolve_fixtures
from model_effort.grader_config import GraderKind

# An arm may cost less than estimated, never more.
MIN_ESTIMATE_TO_ACTUAL = 1.0
# The estimate ignores effort, so a low-effort arm on a small fixture lands
# furthest above its cost; this bounds how far.
MAX_ESTIMATE_TO_ACTUAL = 8.0
# The flat per-trial output allowance fits a review agent's findings report. A
# rubric-graded agent answers in a few hundred tokens, so its estimate lands
# 35x to 55x above its cost; this looser ceiling still catches a runaway.
MAX_RUBRIC_ESTIMATE_TO_ACTUAL = 100.0
# Fewer arms than this means the guard is checking almost nothing.
MIN_ARMS_CHECKED = 10
# Fewer arms under the tight ceiling than this means arms have silently moved
# out from under it.
MIN_TIGHTLY_BOUNDED_ARMS = 50


def _artifacts() -> list[Path]:
    return sorted(paths.RUNS_DIR.glob("*.json"))


def _arm_estimate_usd(
    agent: str, system_prompt: str, arm: dict, pricing: dict
) -> float:
    """Today's estimate for the trials the arm actually ran, fixture by fixture."""
    model_arm = Arm(arm["label"], arm["model_id"], arm["effort"])
    total = 0.0
    for fixture_block in arm["fixtures"]:
        (fixture,) = resolve_fixtures(
            agent, [fixture_block["stem"]], paths.EXPECTED_DIR, paths.FIXTURES_DIR
        )
        run_estimate = estimate.estimate_run(
            [model_arm],
            system_prompt,
            [fixture],
            len(fixture_block["trials"]),
            pricing,
        )
        total += run_estimate.cost_usd_for_arm(model_arm.label)
    return total


def _artifact_ratios(artifact: Path, pricing: dict) -> list[tuple[str, float, bool]]:
    """(arm name, estimate-to-actual ratio, whether the arm is rubric-graded)."""
    written = json.loads(artifact.read_text(encoding="utf-8"))
    is_rubric = written["grader"] == GraderKind.RUBRIC
    agent = written["agent"]
    system_prompt = build_agent_spec(
        agent, load_agent_file(agent, paths.AGENTS_DIR)
    ).system_prompt
    ratios = []
    for arm in written["arms"]:
        totals = arm["totals"]
        if totals["unreported_trials_estimate_usd"] or not totals["actual_cost_usd"]:
            continue
        ratio = (
            _arm_estimate_usd(agent, system_prompt, arm, pricing)
            / totals["actual_cost_usd"]
        )
        ratios.append((f"{artifact.name}:{arm['label']}", ratio, is_rubric))
    return ratios


def _ratios() -> list[tuple[str, float, bool]]:
    external.load_for_run()
    pricing = json.loads(paths.PRICING_PATH.read_text(encoding="utf-8"))
    ratios = []
    for artifact in _artifacts():
        try:
            ratios.extend(_artifact_ratios(artifact, pricing))
        except Exception as error:  # noqa: BLE001  (any failure names the artifact)
            pytest.fail(
                f"cannot re-estimate {artifact.name}: {type(error).__name__}: "
                f"{error}. Its agent, fixtures or model may no longer exist: "
                "recalibrate against a new run, or retire the artifact"
            )
    return ratios


@pytest.fixture(scope="module")
def ratios() -> list[tuple[str, float, bool]]:
    return _ratios()


def test_enough_arms_are_checked(ratios):
    assert len(ratios) >= MIN_ARMS_CHECKED, f"only {len(ratios)} arms checked"


def test_no_arm_cost_more_than_estimated(ratios):
    under = [
        (name, round(ratio, 2))
        for name, ratio, _ in ratios
        if ratio < MIN_ESTIMATE_TO_ACTUAL
    ]

    assert under == [], "the estimate is below what these arms cost: recalibrate"


def test_no_arm_was_estimated_far_above_its_cost(ratios):
    over = [
        (name, round(ratio, 2))
        for name, ratio, is_rubric in ratios
        if ratio
        > (MAX_RUBRIC_ESTIMATE_TO_ACTUAL if is_rubric else MAX_ESTIMATE_TO_ACTUAL)
    ]

    assert over == [], "the estimate is far above what these arms cost: recalibrate"


def test_the_tight_ceiling_covers_enough_arms(ratios):
    tight = sum(1 for *_, is_rubric in ratios if not is_rubric)

    assert tight >= MIN_TIGHTLY_BOUNDED_ARMS, (
        f"only {tight} arms under the {MAX_ESTIMATE_TO_ACTUAL}x ceiling"
    )
