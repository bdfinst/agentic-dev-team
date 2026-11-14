"""How many trials each arm runs (model_effort.trial_count), through the CLI and the resolver."""

from __future__ import annotations

import pytest
from ab_constants import ARM_COUNT
from ab_inputs import make_file_fixture, write_agent_file, write_expected
from ab_stub_claude import StubClaude
from ab_world import World, cli, deps_with_canned_trials, stderr_lines
from model_effort import trial_count
from model_effort.grader_config import GraderKind

EXPECTED_FINDINGS = GraderKind.EXPECTED_FINDINGS


def _add_agent(world: World, name: str) -> None:
    """Add a read-only agent with one fixture, so a run over it has one fixture."""
    write_agent_file(
        world.deps.eval_paths.agents_dir, name, "Read", model="sonnet", effort="high"
    )
    write_expected(world.expected_dir, f"{name}-case", name, "pass")
    make_file_fixture(world.deps.eval_paths.fixtures_dir, f"{name}-case.txt")


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
        deps, trial_calls = deps_with_canned_trials(world.deps)

        code = cli(
            world, StubClaude(world.stub_dir), agent, "--model", "haiku", deps=deps
        )

        assert code == 0
        assert len(trial_calls) == ARM_COUNT * trials
        assert f"Trials per arm per fixture: {trials} ({echo_label})" in stderr_lines(
            capsys
        )

    def test_explicit_trials_override_the_high_stakes_default(self, world, capsys):
        _add_agent(world, "security-review")
        deps, trial_calls = deps_with_canned_trials(world.deps)

        code = cli(
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
        assert "Trials per arm per fixture: 3 (--trials)" in stderr_lines(capsys)

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
