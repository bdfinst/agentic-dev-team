"""Progress and summary rendering (model_effort.report)."""

from __future__ import annotations

from _model_effort_support import (
    ARM_RUN_CALLS,
    BASELINE_TWO_ARM_ESTIMATE,
    CANDIDATE_TWO_ARM_ESTIMATE,
    CLEAN_FORM_ARGS,
    CLI_FAILURE_RECORD,
    FULL_RUN_COST,
    MAX_COST_MID_RUN,
    SCOUT_HAIKU_ARGS,
    SCOUT_TRIALS,
    TRIAL_COST,
    TRIALS_BEFORE_STOP,
    TWO_ARM_ESTIMATE,
    _cli,
    _cli_canned,
    _deps_with_canned_trials,
    _interrupting_deps,
    _passing_stub,
    _stderr_lines,
    _trial_result,
)
from model_effort import outcome, report, run_types
from model_effort.arm import BASELINE_LABEL
from model_effort.formatting import format_usd
from model_effort.outcome import Outcome


def _progress_lines(capsys) -> list[str]:
    return [
        line
        for line in _stderr_lines(capsys)
        if line.startswith(("[baseline]", "[candidate]"))
    ]


class TestRenderProgress:
    def _line(self, result: outcome.TrialResult) -> str:
        return report.render_progress(
            run_types.TrialProgress(
                arm_label=BASELINE_LABEL,
                fixture_number=1,
                fixture_count=2,
                fixture_stem="clean-form",
                trial_number=3,
                trials_per_fixture=4,
                result=result,
            )
        )

    def test_reported_cost_is_shown_in_dollars(self):
        line = self._line(_trial_result(Outcome.PASS, cost=0.0123))

        assert line == "[baseline] fixture 1/2 clean-form trial 3/4: pass $0.0123"

    def test_trial_that_reported_no_cost_says_so_instead_of_a_zero_dollar_figure(self):
        line = self._line(_trial_result(Outcome.TIMEOUT, cost=0.0, cost_reported=False))

        assert line == (
            "[baseline] fixture 1/2 clean-form trial 3/4: timeout cost not reported"
        )

    def test_reported_cost_of_zero_is_still_shown_as_a_figure(self):
        line = self._line(_trial_result(Outcome.PASS, cost=0.0))

        assert line.endswith("pass $0.0000")


class TestProgressAndSummary:
    def test_one_progress_line_per_completed_trial_in_run_order(self, world, capsys):
        deps, _ = _deps_with_canned_trials(world.deps)

        _cli_canned(world, deps, *SCOUT_HAIKU_ARGS, "--trials", "2")

        cost = format_usd(TRIAL_COST)
        assert _progress_lines(capsys) == [
            f"[baseline] fixture 1/2 clean-form trial 1/2: pass {cost}",
            f"[candidate] fixture 1/2 clean-form trial 1/2: pass {cost}",
            f"[baseline] fixture 1/2 clean-form trial 2/2: pass {cost}",
            f"[candidate] fixture 1/2 clean-form trial 2/2: pass {cost}",
            f"[baseline] fixture 2/2 layered-svc trial 1/2: graded_fail {cost}",
            f"[candidate] fixture 2/2 layered-svc trial 1/2: graded_fail {cost}",
            f"[baseline] fixture 2/2 layered-svc trial 2/2: graded_fail {cost}",
            f"[candidate] fixture 2/2 layered-svc trial 2/2: graded_fail {cost}",
        ]

    def test_progress_lines_stop_with_the_run_and_match_the_trials_that_completed(
        self, world, capsys
    ):
        deps, trial_calls = _deps_with_canned_trials(world.deps)

        _cli_canned(
            world,
            deps,
            *CLEAN_FORM_ARGS,
            "--trials",
            "5",
            "--max-cost",
            str(MAX_COST_MID_RUN),
        )

        assert len(_progress_lines(capsys)) == len(trial_calls) == TRIALS_BEFORE_STOP

    def test_progress_line_is_printed_before_the_next_trial_starts(self, world, capsys):
        _cli(
            world,
            _passing_stub(world),
            *CLEAN_FORM_ARGS,
            "--trials",
            "5",
            deps=_interrupting_deps(world, 1),
        )

        assert _progress_lines(capsys) == [
            f"[baseline] fixture 1/1 clean-form trial 1/5: pass {format_usd(TRIAL_COST)}"
        ]

    def test_summary_shows_per_arm_outcome_totals_and_actual_against_estimated_cost(
        self, world, capsys
    ):
        deps, _ = _deps_with_canned_trials(world.deps)

        _cli_canned(world, deps, *SCOUT_HAIKU_ARGS, "--trials", str(SCOUT_TRIALS))

        err = capsys.readouterr().err
        arm_cost = format_usd(ARM_RUN_CALLS * TRIAL_COST)
        assert (
            "Summary:\n"
            "  baseline: timeout 0, cli_error 0, tool_violation 0, parse_failure 0, "
            f"graded_fail {SCOUT_TRIALS}, pass {SCOUT_TRIALS}; cost {arm_cost}, "
            f"estimated {format_usd(BASELINE_TWO_ARM_ESTIMATE)}\n"
            "  candidate: timeout 0, cli_error 0, tool_violation 0, parse_failure 0, "
            f"graded_fail {SCOUT_TRIALS}, pass {SCOUT_TRIALS}; cost {arm_cost}, "
            f"estimated {format_usd(CANDIDATE_TWO_ARM_ESTIMATE)}\n"
            f"  total: cost {format_usd(FULL_RUN_COST)}, "
            f"estimated {format_usd(TWO_ARM_ESTIMATE)}\n"
            f"artifact written: {world.artifact_path}\n"
        ) in err

    def test_summary_marks_an_arms_cost_as_a_lower_bound_when_a_trial_reported_none(
        self, world, capsys
    ):
        deps, _ = _deps_with_canned_trials(
            world.deps, overrides={2: CLI_FAILURE_RECORD}
        )

        _cli_canned(world, deps, *CLEAN_FORM_ARGS, "--trials", "3")

        lines = capsys.readouterr().err.splitlines()
        baseline = next(
            line for line in lines if line.startswith("  baseline: timeout")
        )
        candidate = next(
            line for line in lines if line.startswith("  candidate: timeout")
        )
        assert "(lower bound; $" in baseline
        assert "charged as estimate for trials with no reported cost)" in baseline
        assert "lower bound" not in candidate

    def test_incomplete_run_summary_counts_only_completed_trials(self, world, capsys):
        deps, _ = _deps_with_canned_trials(world.deps)

        _cli_canned(
            world,
            deps,
            *CLEAN_FORM_ARGS,
            "--trials",
            "5",
            "--max-cost",
            str(MAX_COST_MID_RUN),
        )

        err = capsys.readouterr().err
        assert (
            f"  total: cost {format_usd(TRIALS_BEFORE_STOP * TRIAL_COST)}, estimated "
            in err
        )
