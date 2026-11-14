"""A stress-matrix run for one agent: plan the three arms, run them, record the verdict."""

from __future__ import annotations

import dataclasses

import pytest
from _model_effort_support import (
    NOW,
    TEST_PRICING,
    FixedRng,
    _cli_canned,
    _deps_with_canned_trials,
    _stderr_lines,
    _written,
)
from model_effort import plan
from model_effort.arm import BASELINE_LABEL, Arm
from model_effort.errors import UsageError
from model_effort.stress_arms import STEP_DOWN_LABEL, STEP_UP_LABEL, Axis
from model_effort.verdict import DECISION_DOWNGRADE

OPUS_PRICING = {
    "models": {**TEST_PRICING["models"], "test-top": {"input": 8.0, "output": 40.0}},
    "aliases": {**TEST_PRICING["aliases"], "opus": "test-top"},
}


def _stress_plan(world, axis=Axis.MODEL, **overrides):
    kwargs = {
        "candidate_model": None,
        "candidate_effort": None,
        "fixture_stems": None,
        "runs_dir": world.runs_dir,
        "now": NOW,
        "rng": FixedRng(),
        "git_sha": None,
        "eval_paths": world.deps.eval_paths,
        "stress_axis": axis,
        **overrides,
    }
    return plan.plan_run("scout", **kwargs)


def test_stress_plan_runs_current_step_down_and_step_up(world):
    with _stress_plan(world) as planned:
        assert planned.arms == (
            Arm(BASELINE_LABEL, "sonnet", "high"),
            Arm(STEP_DOWN_LABEL, "haiku", "high"),
            Arm(STEP_UP_LABEL, "opus", "high"),
        )
        assert planned.stress is True
        assert planned.metadata.run_id == "20261008T123045Z-scout-sonnet-high-0ab3"


def test_stress_plan_on_the_effort_axis_keeps_the_model(world):
    with _stress_plan(world, Axis.EFFORT) as planned:
        assert [(a.model, a.effort) for a in planned.arms] == [
            ("sonnet", "high"),
            ("sonnet", "medium"),
            ("sonnet", "xhigh"),
        ]


def test_stress_plan_refuses_an_explicit_candidate(world):
    with (
        pytest.raises(UsageError, match="--stress"),
        _stress_plan(world, candidate_model="haiku"),
    ):
        pass


def test_ab_plan_is_not_a_stress_plan(scout_plan):
    assert scout_plan.stress is False


def _stress_cli(world, *args):
    deps = dataclasses.replace(world.deps, pricing_table=OPUS_PRICING)
    deps, calls = _deps_with_canned_trials(deps)
    code = _cli_canned(world, deps, "scout", "--stress", "--trials", "2", *args)
    return code, calls


def test_stress_cli_runs_every_arm_and_writes_the_verdict(world):
    code, calls = _stress_cli(world)

    written = _written(world)
    assert code == 0
    # two fixtures, two trials, three arms
    assert len(calls) == 12
    assert written["mode"] == "stress"
    assert [arm["label"] for arm in written["arms"]] == [
        BASELINE_LABEL,
        STEP_DOWN_LABEL,
        STEP_UP_LABEL,
    ]
    assert written["verdict"]["decision"] == DECISION_DOWNGRADE
    assert (written["verdict"]["model"], written["verdict"]["effort"]) == (
        "haiku",
        "high",
    )


def test_stress_cli_prints_the_verdict_and_its_reason(world, capsys):
    _stress_cli(world)

    lines = _stderr_lines(capsys)
    assert any(line.startswith("Verdict: downgrade to haiku/high") for line in lines), (
        lines
    )


def test_ab_cli_writes_no_verdict(world):
    deps, _ = _deps_with_canned_trials(world.deps)
    _cli_canned(world, deps, "scout", "--model", "haiku", "--trials", "1")

    written = _written(world)
    assert "verdict" not in written
    assert "mode" not in written


def test_stress_flag_and_model_flag_together_are_a_usage_error(world, capsys):
    code, calls = _stress_cli(world, "--model", "haiku")

    assert (code, calls) == (2, [])
    assert "--stress" in capsys.readouterr().err
