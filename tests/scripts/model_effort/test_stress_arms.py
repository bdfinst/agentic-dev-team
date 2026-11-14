"""The stress matrix's arms (model_effort.stress_arms): one step down and one step up from the current tier."""

from __future__ import annotations

import _model_effort_support  # noqa: F401  (puts the harness on sys.path first)
import pytest
from model_effort.arm import BASELINE_LABEL, Arm
from model_effort.stress_arms import (
    STEP_DOWN_LABEL,
    STEP_UP_LABEL,
    Axis,
    stress_arms,
)


def _arms(model: str, effort: str, axis: Axis = Axis.MODEL) -> dict[str, Arm]:
    return {arm.label: arm for arm in stress_arms(model, effort, axis)}


@pytest.mark.parametrize(
    ("model", "down", "up"),
    [
        ("sonnet", ("haiku", "high"), ("opus", "high")),
        ("claude-sonnet-5-5", ("haiku", "high"), ("opus", "high")),
    ],
)
def test_model_axis_steps_one_model_tier_each_way_at_the_same_effort(model, down, up):
    arms = _arms(model, "high")

    assert arms[BASELINE_LABEL] == Arm(BASELINE_LABEL, model, "high")
    assert (arms[STEP_DOWN_LABEL].model, arms[STEP_DOWN_LABEL].effort) == down
    assert (arms[STEP_UP_LABEL].model, arms[STEP_UP_LABEL].effort) == up


def test_model_axis_steps_effort_down_when_no_lower_model_exists():
    arms = _arms("haiku", "high")

    assert arms[STEP_DOWN_LABEL] == Arm(STEP_DOWN_LABEL, "haiku", "medium")
    assert arms[STEP_UP_LABEL] == Arm(STEP_UP_LABEL, "sonnet", "high")


def test_model_axis_steps_effort_up_when_no_higher_model_exists():
    arms = _arms("opus", "high")

    assert arms[STEP_DOWN_LABEL] == Arm(STEP_DOWN_LABEL, "sonnet", "high")
    assert arms[STEP_UP_LABEL] == Arm(STEP_UP_LABEL, "opus", "xhigh")


def test_effort_axis_keeps_the_model_and_moves_effort_one_level():
    arms = _arms("sonnet", "medium", Axis.EFFORT)

    assert arms[STEP_DOWN_LABEL] == Arm(STEP_DOWN_LABEL, "sonnet", "low")
    assert arms[STEP_UP_LABEL] == Arm(STEP_UP_LABEL, "sonnet", "high")


def test_an_arm_with_no_step_left_on_either_ladder_is_left_out():
    arms = _arms("haiku", "low")

    assert set(arms) == {BASELINE_LABEL, STEP_UP_LABEL}


def test_effort_axis_at_the_top_effort_has_no_step_up():
    arms = _arms("opus", "max", Axis.EFFORT)

    assert set(arms) == {BASELINE_LABEL, STEP_DOWN_LABEL}


def test_the_current_arm_comes_first():
    assert stress_arms("sonnet", "high", Axis.MODEL)[0].label == BASELINE_LABEL


def test_a_model_off_the_ladder_steps_on_effort_only():
    arms = _arms("fable", "high")

    assert arms[STEP_DOWN_LABEL] == Arm(STEP_DOWN_LABEL, "fable", "medium")
    assert arms[STEP_UP_LABEL] == Arm(STEP_UP_LABEL, "fable", "xhigh")


def test_effort_axis_steps_the_model_up_when_no_higher_effort_exists():
    arms = _arms("sonnet", "max", Axis.EFFORT)

    assert arms[STEP_DOWN_LABEL] == Arm(STEP_DOWN_LABEL, "sonnet", "xhigh")
    assert arms[STEP_UP_LABEL] == Arm(STEP_UP_LABEL, "opus", "max")


def test_effort_axis_steps_the_model_down_when_no_lower_effort_exists():
    arms = _arms("sonnet", "low", Axis.EFFORT)

    assert arms[STEP_DOWN_LABEL] == Arm(STEP_DOWN_LABEL, "haiku", "low")
    assert arms[STEP_UP_LABEL] == Arm(STEP_UP_LABEL, "sonnet", "medium")


def test_model_axis_at_the_top_of_both_ladders_has_no_step_up():
    arms = _arms("opus", "max")

    assert arms == {
        BASELINE_LABEL: Arm(BASELINE_LABEL, "opus", "max"),
        STEP_DOWN_LABEL: Arm(STEP_DOWN_LABEL, "sonnet", "max"),
    }


@pytest.mark.parametrize("axis", list(Axis))
def test_an_effort_off_the_ladder_steps_on_the_model_only(axis):
    arms = _arms("sonnet", "turbo", axis)

    assert arms[STEP_DOWN_LABEL] == Arm(STEP_DOWN_LABEL, "haiku", "turbo")
    assert arms[STEP_UP_LABEL] == Arm(STEP_UP_LABEL, "opus", "turbo")


def test_off_both_ladders_has_no_step_either_way():
    assert set(_arms("fable", "turbo", Axis.EFFORT)) == {BASELINE_LABEL}


def _committed_rubric_agents() -> list[str]:
    from model_effort import grader_config, paths

    return sorted(
        agent
        for agent, entry in grader_config.load_grader_map(paths.GRADER_MAP_PATH).items()
        if grader_config.entry_grader(entry) == "rubric"
    )


@pytest.mark.parametrize("agent", _committed_rubric_agents())
def test_each_committed_rubric_judge_can_judge_the_agents_stress_arms(agent):
    from model_effort import grader_config, judge_tier, paths
    from model_effort.agent_file import load_agent_file
    from model_effort.agent_spec import build_agent_spec

    spec = build_agent_spec(agent, load_agent_file(agent, paths.AGENTS_DIR))
    grading = grader_config.resolve_agent_grading(agent, paths.GRADER_MAP_PATH)
    arms = stress_arms(spec.model, spec.effort, Axis.MODEL)

    judge_tier.check_judge_tier(grading.judge, [arm.model for arm in arms])
