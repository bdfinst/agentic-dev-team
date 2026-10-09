"""Spend refusals and the approval gate (model_effort.approval)."""

from __future__ import annotations

import io

import pytest
from _model_effort_support import (
    ARM_COUNT,
    FULL_RUN_CALLS,
    FULL_RUN_COST,
    MAX_COST_BELOW_ESTIMATE,
    SCOUT_FIXTURE_COUNT,
    SCOUT_HAIKU_ARGS,
    SCOUT_TRIALS,
    TWO_ARM_ESTIMATE,
    RaisingStdin,
    StubClaude,
    World,
    _cli,
    _deps_with_canned_trials,
    _gated_deps,
    _passing_stub,
    _stderr_lines,
    assert_nothing_ran,
)
from model_effort.formatting import format_usd

MAX_COST_ABOVE_FULL_RUN = 2 * FULL_RUN_COST
SINGLE_TRIAL_RUN_CALLS = ARM_COUNT * SCOUT_FIXTURE_COUNT


def _run_over_max_cost(world: World, stub: StubClaude, **cli_options) -> int:
    """Run the CLI with a spend limit under the run's estimate, so startup refuses it."""
    return _cli(
        world,
        stub,
        *SCOUT_HAIKU_ARGS,
        "--trials",
        str(SCOUT_TRIALS),
        "--max-cost",
        str(MAX_COST_BELOW_ESTIMATE),
        **cli_options,
    )


class TestSpendRefusals:
    def test_unpriced_candidate_exits_2_naming_it_with_no_trial_and_no_placeholder(
        self, world, capsys
    ):
        stub = StubClaude(world.stub_dir)

        code = _cli(world, stub, "scout", "--model", "opus")

        stderr = capsys.readouterr().err
        assert code == 2
        assert "'opus' (candidate arm)" in stderr
        assert "sonnet" not in stderr
        assert_nothing_ran(stub, world)

    def test_estimate_above_max_cost_exits_2_naming_both_figures_with_no_trial_and_no_placeholder(
        self, world, capsys
    ):
        stub = StubClaude(world.stub_dir)

        code = _run_over_max_cost(world, stub, yes=True)

        stderr = capsys.readouterr().err
        assert code == 2
        assert format_usd(TWO_ARM_ESTIMATE) in stderr
        assert format_usd(MAX_COST_BELOW_ESTIMATE) in stderr
        assert_nothing_ran(stub, world)

    def test_refused_run_still_printed_the_configuration_and_estimate(
        self, world, capsys
    ):
        stub = StubClaude(world.stub_dir)

        _run_over_max_cost(world, stub)

        lines = _stderr_lines(capsys)
        assert "Agent: scout" in lines
        assert any(line.startswith("Estimate (rough") for line in lines)

    def test_estimate_below_max_cost_runs(self, world):
        stub = _passing_stub(world)

        code = _cli(
            world,
            stub,
            *SCOUT_HAIKU_ARGS,
            "--trials",
            str(SCOUT_TRIALS),
            "--max-cost",
            str(MAX_COST_ABOVE_FULL_RUN),
        )

        assert code == 0
        assert len(stub.calls) == FULL_RUN_CALLS

    @pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "cheap"])
    def test_max_cost_that_is_not_a_positive_number_is_a_usage_error(
        self, world, value
    ):
        stub = StubClaude(world.stub_dir)

        with pytest.raises(SystemExit) as excinfo:
            _cli(world, stub, "scout", "--max-cost", value)

        assert excinfo.value.code == 2
        assert_nothing_ran(stub, world)


DECLINED_MESSAGE = (
    "error: declined at the prompt, so no trial ran: rerun and answer y, or pass --yes"
)


class TestApprovalGate:
    def _run(self, world, stdin, *, is_tty=True, yes=False) -> tuple[int, list[tuple]]:
        """Run one trial per arm behind the gate; return the exit code and the trials that ran."""
        deps, trial_calls = _deps_with_canned_trials(
            _gated_deps(world, stdin, is_tty=is_tty)
        )
        code = _cli(
            world,
            StubClaude(world.stub_dir),
            *SCOUT_HAIKU_ARGS,
            "--trials",
            "1",
            yes=yes,
            deps=deps,
        )
        return code, trial_calls

    def test_yes_flag_runs_trials_without_prompting_or_reading_stdin(
        self, world, capsys
    ):
        stdin = RaisingStdin(AssertionError("stdin must not be read"))

        code, trial_calls = self._run(world, stdin, yes=True)

        assert code == 0
        assert len(trial_calls) == SINGLE_TRIAL_RUN_CALLS
        assert "Proceed?" not in capsys.readouterr().err

    def test_yes_flag_runs_trials_when_stdin_is_not_a_tty(self, world):
        code, trial_calls = self._run(world, io.StringIO(""), is_tty=False, yes=True)

        assert code == 0
        assert len(trial_calls) == SINGLE_TRIAL_RUN_CALLS

    @pytest.mark.parametrize("answer", ["y", "yes", " YES ", "Y", "Yes\t"])
    def test_affirmative_answer_prompts_on_stderr_then_runs_trials(
        self, world, capsys, answer
    ):
        code, trial_calls = self._run(world, io.StringIO(f"{answer}\n"))

        err = capsys.readouterr().err
        assert code == 0
        assert err.index("Estimate (rough") < err.index("Proceed? [y/N] ")
        assert err.index("Proceed? [y/N] ") < err.index("artifact written")
        assert len(trial_calls) == SINGLE_TRIAL_RUN_CALLS

    @pytest.mark.parametrize(
        "answer", ["n", "no", "", "  ", "ye", "yess", "yes please"]
    )
    def test_any_other_answer_exits_1_with_one_line_message_and_no_trial(
        self, world, capsys, answer
    ):
        code, trial_calls = self._run(world, io.StringIO(f"{answer}\n"))

        assert code == 1
        assert capsys.readouterr().err.endswith(DECLINED_MESSAGE + "\n")
        assert (trial_calls, world.artifacts) == ([], [])

    def test_end_of_input_at_the_prompt_declines_on_its_own_line_with_no_trial(
        self, world, capsys
    ):
        code, trial_calls = self._run(world, io.StringIO(""))

        assert code == 1
        assert capsys.readouterr().err.endswith("\n" + DECLINED_MESSAGE + "\n")
        assert (trial_calls, world.artifacts) == ([], [])

    def test_ctrl_c_at_the_prompt_declines_with_no_trial_and_no_traceback(
        self, world, capsys
    ):
        code, trial_calls = self._run(world, RaisingStdin(KeyboardInterrupt()))

        err = capsys.readouterr().err
        assert code == 1
        assert err.endswith("\n" + DECLINED_MESSAGE + "\n")
        assert "Traceback" not in err
        assert (trial_calls, world.artifacts) == ([], [])

    def test_no_tty_without_yes_prints_the_estimate_then_exits_1_telling_how_to_proceed(
        self, world, capsys
    ):
        stdin = RaisingStdin(AssertionError("stdin must not be read"))

        code, trial_calls = self._run(world, stdin, is_tty=False)

        lines = capsys.readouterr().err.splitlines()
        assert code == 1
        assert any(line.startswith("Estimate (rough") for line in lines)
        assert lines[-1] == (
            "error: approval required and stdin is not a TTY: rerun with --yes"
        )
        assert (trial_calls, world.artifacts) == ([], [])

    def test_estimate_above_max_cost_exits_2_before_prompting(self, world, capsys):
        stub = _passing_stub(world)
        stdin = RaisingStdin(AssertionError("stdin must not be read"))

        code = _run_over_max_cost(
            world, stub, yes=False, deps=_gated_deps(world, stdin)
        )

        assert code == 2
        assert "Proceed?" not in capsys.readouterr().err
        assert_nothing_ran(stub, world)
