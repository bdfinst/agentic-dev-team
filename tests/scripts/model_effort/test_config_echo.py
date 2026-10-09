"""The configuration echo printed before a run (model_effort.config_echo)."""

from __future__ import annotations

import dataclasses

from _model_effort_support import (
    BASELINE_TWO_ARM_ESTIMATE,
    CANDIDATE_TWO_ARM_ESTIMATE,
    CLEAN_FORM_ARGS,
    SCOUT_HAIKU_ARGS,
    SCOUT_TRIALS,
    TWO_ARM_ESTIMATE,
    StubClaude,
    _cli,
    _deps_with_canned_trials,
    _make_file_fixture,
    _passing_stub,
    _stderr_lines,
    _write_agent,
    _write_expected,
)
from model_effort import runner
from model_effort.formatting import format_usd


class TestConfigurationEcho:
    def test_stderr_shows_agent_arms_tools_fixtures_trials_timeout_and_estimate(
        self, world, capsys
    ):
        stub = _passing_stub(world)

        _cli(world, stub, *SCOUT_HAIKU_ARGS, "--trials", str(SCOUT_TRIALS))

        assert _stderr_lines(capsys)[:9] == [
            "Agent: scout",
            "Arms:",
            "  baseline: model sonnet, effort high",
            "  candidate: model haiku, effort high",
            "Tools: Read, Grep",
            "Withheld tools: mcp__x__y, Bash(graphify *)",
            "Fixtures: clean-form, layered-svc",
            "Trials per arm per fixture: 3 (--trials)",
            "Trial timeout: 600 s",
        ]

    def test_estimate_line_labels_the_figure_rough_and_lists_each_arm_and_the_total(
        self, world, capsys
    ):
        stub = _passing_stub(world)

        _cli(world, stub, *SCOUT_HAIKU_ARGS, "--trials", str(SCOUT_TRIALS))

        assert (
            "Estimate (rough; real cost can be several times off, high or low): "
            f"baseline {format_usd(BASELINE_TWO_ARM_ESTIMATE)}, "
            f"candidate {format_usd(CANDIDATE_TWO_ARM_ESTIMATE)}, "
            f"total {format_usd(TWO_ARM_ESTIMATE)}"
        ) in _stderr_lines(capsys)

    def test_trial_timeout_flag_reaches_every_trial_and_the_echo(self, world, capsys):
        deps, trial_calls = _deps_with_canned_trials(world.deps)

        code = _cli(
            world,
            StubClaude(world.stub_dir),
            *CLEAN_FORM_ARGS,
            "--trials",
            "1",
            "--trial-timeout",
            "7",
            deps=deps,
        )

        assert code == 0
        assert [timeout for _fixture, _config, timeout in trial_calls] == [7, 7]
        assert "Trial timeout: 7 s" in _stderr_lines(capsys)

    def test_trials_line_says_default_when_the_flag_is_absent(self, world, capsys):
        stub = _passing_stub(world)

        _cli(world, stub, *CLEAN_FORM_ARGS)

        assert "Trials per arm per fixture: 5 (default)" in _stderr_lines(capsys)

    def test_agent_without_tools_prints_no_tools_enabled_and_withheld_none(
        self, world, capsys
    ):
        _write_agent(
            world.deps.eval_paths.agents_dir,
            "bare",
            None,
            model="sonnet",
            effort="high",
        )
        _write_expected(world.expected_dir, "bare-fixture", "bare", "pass")
        _make_file_fixture(world.deps.eval_paths.fixtures_dir, "bare-fixture.txt")
        stub = _passing_stub(world)

        _cli(world, stub, "bare", "--model", "haiku", "--trials", "1")

        lines = _stderr_lines(capsys)
        assert "Tools: no tools enabled" in lines
        assert "Withheld tools: none" in lines

    def test_echo_is_already_printed_when_the_first_trial_starts(self, world, capsys):
        stderr_when_trials_start = []

        def snapshot_then_run(*args, **kwargs):
            stderr_when_trials_start.append(capsys.readouterr().err)
            return runner.run_trial(*args, **kwargs)

        _cli(
            world,
            _passing_stub(world),
            *CLEAN_FORM_ARGS,
            "--trials",
            "1",
            deps=dataclasses.replace(world.deps, run_trial=snapshot_then_run),
        )

        assert (
            "Estimate (rough; real cost can be several times off, high or low)"
            in stderr_when_trials_start[0]
        )
