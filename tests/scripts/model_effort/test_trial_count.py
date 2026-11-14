"""How many trials each arm runs (model_effort.trial_count), through the CLI and the resolver."""

from __future__ import annotations

import pytest
from _model_effort_support import (
    ARM_COUNT,
    StubClaude,
    World,
    _cli,
    _deps_with_canned_trials,
    _make_file_fixture,
    _stderr_lines,
    _write_agent,
    _write_expected,
)
from model_effort import trial_count
from model_effort.grader_config import GraderKind

EXPECTED_FINDINGS = GraderKind.EXPECTED_FINDINGS


def _add_agent(world: World, name: str) -> None:
    """Add a read-only agent with one fixture, so a run over it has one fixture."""
    _write_agent(
        world.deps.eval_paths.agents_dir, name, "Read", model="sonnet", effort="high"
    )
    _write_expected(world.expected_dir, f"{name}-case", name, "pass")
    _make_file_fixture(world.deps.eval_paths.fixtures_dir, f"{name}-case.txt")


class TestTrialDefaults:
    @pytest.mark.parametrize(
        ("agent", "trials", "echo_label"),
        [
            ("naming-review", 5, "default"),
            ("security-review", 10, "high-stakes default"),
        ],
    )
    def test_each_arm_runs_the_default_trials_for_the_agent(
        self, world, capsys, agent, trials, echo_label
    ):
        _add_agent(world, agent)
        deps, trial_calls = _deps_with_canned_trials(world.deps)

        code = _cli(
            world, StubClaude(world.stub_dir), agent, "--model", "haiku", deps=deps
        )

        assert code == 0
        assert len(trial_calls) == ARM_COUNT * trials
        assert f"Trials per arm per fixture: {trials} ({echo_label})" in _stderr_lines(
            capsys
        )

    def test_explicit_trials_override_the_high_stakes_default(self, world, capsys):
        _add_agent(world, "security-review")
        deps, trial_calls = _deps_with_canned_trials(world.deps)

        code = _cli(
            world,
            StubClaude(world.stub_dir),
            "security-review",
            "--model",
            "haiku",
            "--trials",
            "3",
            deps=deps,
        )

        assert code == 0
        assert len(trial_calls) == ARM_COUNT * 3
        assert "Trials per arm per fixture: 3 (--trials)" in _stderr_lines(capsys)

    @pytest.mark.parametrize(
        "agent",
        ["security-review", "correctness-review", "architect", "security-engineer"],
    )
    def test_resolver_gives_every_high_stakes_agent_ten_trials(self, agent):
        assert trial_count.resolve_trials(
            None, agent, EXPECTED_FINDINGS
        ) == trial_count.TrialCount(10, "high-stakes default")

    def test_resolver_gives_other_agents_five_trials(self):
        assert trial_count.resolve_trials(
            None, "security-reviewer", EXPECTED_FINDINGS
        ) == (trial_count.TrialCount(5, "default"))

    def test_resolver_prefers_the_flag_over_the_high_stakes_default(self):
        assert trial_count.resolve_trials(
            2, "architect", EXPECTED_FINDINGS
        ) == trial_count.TrialCount(2, "--trials")
