"""Stop rules (model_effort.stop_rules): ending a run early and keeping the partial results."""

from __future__ import annotations

import dataclasses

import model_effort_ab
import pytest
from _model_effort_support import (
    ARM_COUNT,
    ARM_RUN_CALLS,
    BASELINE_TWO_ARM_ESTIMATE,
    CAUSE_LIMIT,
    CLEAN_FORM_ARGS,
    CLI_FAILURE_RECORD,
    FULL_RUN_CALLS,
    MAX_COST_MID_RUN,
    SCOUT_HAIKU_ARGS,
    SCOUT_TRIALS,
    TIMED_OUT_RECORD,
    TRIAL_COST,
    TRIALS_BEFORE_STOP,
    TWO_ARM_ESTIMATE,
    World,
    _arm_block,
    _cli_canned,
    _deps_timing_out,
    _deps_with_canned_trials,
    _outcomes,
    _written,
    assert_cut_at_limit,
)
from model_effort import stop_rules
from model_effort.arm import BASELINE_LABEL, CANDIDATE_LABEL
from model_effort.outcome import Outcome
from model_effort.run_status import AbortReason, RunStatus
from model_effort.stop_rules import SpendLimit

# A spend limit just above the run's estimate, so the startup refusal allows it.
MAX_COST_ESTIMATE_FACTOR = 1.1
# Calls alternate baseline, candidate; the baseline's every second trial reports no
# cost, which is one call in four of the full run.
UNREPORTED_CALLS = FULL_RUN_CALLS // 4
REPORTED_CALLS = FULL_RUN_CALLS - UNREPORTED_CALLS
# Each reported trial costs a share of the limit that leaves half a share spare, so
# the reported trials alone stay under the limit.
SPARE_TRIAL_SHARE = 0.5


PASS, GRADED_FAIL = Outcome.PASS, Outcome.GRADED_FAIL
CLI_ERROR, TIMEOUT = Outcome.CLI_ERROR, Outcome.TIMEOUT
INFRA_FAILURE, MAX_COST = AbortReason.INFRA_FAILURE, AbortReason.MAX_COST


def _check(
    baseline=(), candidate=(), charged_usd=0.0, max_cost_usd=None, trials_remaining=1
):
    spend_limit = None if max_cost_usd is None else SpendLimit(max_cost_usd)
    return stop_rules.check_stop(
        {BASELINE_LABEL: list(baseline), CANDIDATE_LABEL: list(candidate)},
        charged_usd,
        spend_limit,
        trials_remaining=trials_remaining,
    )


class TestSpendLimit:
    def test_estimate_above_the_limit_is_refused_and_one_equal_to_it_is_not(self):
        limit = SpendLimit(0.5)

        assert limit.refuses(0.75) is True
        assert limit.refuses(0.5) is False

    def test_cost_above_the_limit_exceeds_it_and_one_equal_to_it_does_not(self):
        limit = SpendLimit(0.5)

        assert limit.exceeded_by(0.75) is True
        assert limit.exceeded_by(0.5) is False


class TestRunStatus:
    def test_a_run_is_complete_exactly_when_nothing_ended_it_early(self):
        assert RunStatus.of(None) is RunStatus.COMPLETE
        assert all(
            RunStatus.of(reason) is RunStatus.INCOMPLETE for reason in AbortReason
        )


class TestStopRules:
    def test_cost_strictly_above_max_cost_stops_for_max_cost(self):
        assert _check([PASS], [PASS], charged_usd=0.75, max_cost_usd=0.5) == MAX_COST

    def test_cost_equal_to_max_cost_does_not_stop(self):
        assert _check([PASS], [PASS], charged_usd=0.5, max_cost_usd=0.5) is None

    def test_any_cost_is_allowed_without_a_max_cost(self):
        assert (
            _check([PASS], [PASS], charged_usd=1_000_000.0, max_cost_usd=None) is None
        )

    def test_no_trials_yet_does_not_stop(self):
        assert _check() is None

    @pytest.mark.parametrize("outcome", [CLI_ERROR, TIMEOUT])
    def test_first_trial_of_the_baseline_arm_ending_in_an_infra_outcome_stops(
        self, outcome
    ):
        assert _check([outcome]) == INFRA_FAILURE

    @pytest.mark.parametrize("outcome", [CLI_ERROR, TIMEOUT])
    def test_first_trial_of_the_candidate_arm_ending_in_an_infra_outcome_stops(
        self, outcome
    ):
        assert _check([PASS], [outcome]) == INFRA_FAILURE

    def test_a_non_infra_failure_on_the_first_trial_does_not_stop(self):
        assert _check([GRADED_FAIL], [Outcome.TOOL_VIOLATION]) is None

    def test_single_later_cli_error_does_not_stop(self):
        assert _check([PASS, CLI_ERROR], [PASS, PASS]) is None

    def test_three_consecutive_infra_outcomes_in_one_arm_stop(self):
        assert _check([PASS, CLI_ERROR, TIMEOUT, CLI_ERROR]) == INFRA_FAILURE

    def test_two_consecutive_infra_outcomes_do_not_stop(self):
        assert _check([PASS, CLI_ERROR, TIMEOUT]) is None

    def test_a_pass_between_infra_outcomes_resets_the_count(self):
        history = [PASS, CLI_ERROR, CLI_ERROR, PASS, CLI_ERROR, CLI_ERROR]

        assert _check(history) is None

    def test_a_graded_failure_between_infra_outcomes_resets_the_count(self):
        history = [PASS, CLI_ERROR, CLI_ERROR, GRADED_FAIL, CLI_ERROR]

        assert _check(history) is None

    def test_infra_failures_alternating_across_arms_stop_only_when_one_arm_has_three(
        self,
    ):
        # Run order: B fail, C pass, B fail, C pass, B fail. B's own third fails.
        assert _check([PASS, CLI_ERROR], [PASS, PASS]) is None
        assert _check([PASS, CLI_ERROR, CLI_ERROR], [PASS, PASS]) is None
        assert (
            _check([PASS, CLI_ERROR, CLI_ERROR, CLI_ERROR], [PASS, PASS])
            == INFRA_FAILURE
        )

    def test_infra_failures_spread_over_two_arms_never_add_up(self):
        assert _check([PASS, CLI_ERROR, CLI_ERROR], [PASS, TIMEOUT, TIMEOUT]) is None

    def test_a_stop_condition_on_the_last_planned_trial_is_not_a_stop(self):
        assert (
            _check([CLI_ERROR], charged_usd=2.0, max_cost_usd=1.0, trials_remaining=0)
            is None
        )
        assert _check([CLI_ERROR], trials_remaining=0) is None

    def test_a_stop_condition_with_a_trial_still_to_run_stops(self):
        assert _check([CLI_ERROR], trials_remaining=1) == INFRA_FAILURE

    def test_max_cost_wins_when_the_infra_rule_also_applies(self):
        assert _check([CLI_ERROR], charged_usd=2.0, max_cost_usd=1.0) == MAX_COST


def _deps_always_failing(
    world: World, outcome_name: str
) -> tuple[model_effort_ab.Deps, list[tuple]]:
    """Deps under which every trial ends in `outcome_name` (cli_error or timeout)."""
    record = TIMED_OUT_RECORD if outcome_name == "timeout" else CLI_FAILURE_RECORD
    return _deps_with_canned_trials(world.deps, default=record)


class TestSpendLimitStop:
    def test_run_stops_after_the_trial_that_passes_max_cost_and_starts_no_more(
        self, world
    ):
        deps, trial_calls = _deps_with_canned_trials(world.deps)

        code = _cli_canned(
            world,
            deps,
            *CLEAN_FORM_ARGS,
            "--trials",
            "5",
            "--max-cost",
            str(MAX_COST_MID_RUN),
        )

        written = _written(world)
        assert code == 1
        assert len(trial_calls) == TRIALS_BEFORE_STOP
        assert (written["status"], written["abort_reason"]) == (
            "incomplete",
            "max-cost",
        )
        assert _outcomes(written, BASELINE_LABEL) == ["pass", "pass"]
        assert _outcomes(written, CANDIDATE_LABEL) == ["pass"]

    def test_incomplete_totals_count_only_the_completed_trials(self, world):
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

        written = _written(world)
        assert _arm_block(written, BASELINE_LABEL)["totals"]["pass"] == 2
        assert _arm_block(written, BASELINE_LABEL)["totals"][
            "actual_cost_usd"
        ] == pytest.approx(2 * TRIAL_COST)
        assert _arm_block(written, CANDIDATE_LABEL)["totals"]["pass"] == 1

    def test_stderr_names_the_abort_reason_and_the_artifact_path(self, world, capsys):
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
        assert "run stopped early (max-cost)" in err
        assert f"artifact written: {world.artifact_path}" in err

    def test_stop_notice_says_charged_cost_because_the_limit_counts_estimates(
        self, world, capsys
    ):
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
        assert "charged cost passed --max-cost" in err
        assert "actual cost" not in err

    def test_max_cost_help_says_the_run_stops_on_charged_cost(self):
        help_text = " ".join(model_effort_ab._build_parser().format_help().split())

        assert "run once the charged cost (" in help_text
        assert "actual cost" not in help_text

    def test_charged_cost_equal_to_max_cost_lets_the_run_finish(self, world):
        deps, trial_calls = _deps_with_canned_trials(world.deps)

        code = _cli_canned(
            world,
            deps,
            *CLEAN_FORM_ARGS,
            "--trials",
            "1",
            "--max-cost",
            str(ARM_COUNT * TRIAL_COST),
        )

        assert code == 0
        assert len(trial_calls) == ARM_COUNT
        assert _written(world)["status"] == "complete"

    @staticmethod
    def _run_with_unreported_baseline_trials(world, kind):
        """Run to a limit the reported costs never pass, with the baseline's unreported trials charged."""
        limit = MAX_COST_ESTIMATE_FACTOR * TWO_ARM_ESTIMATE
        reported_cost = limit / (REPORTED_CALLS + SPARE_TRIAL_SHARE)
        failure = TIMED_OUT_RECORD if kind == "timeout" else CLI_FAILURE_RECORD
        unreported_calls = range(2, FULL_RUN_CALLS, 4)
        deps, _ = _deps_with_canned_trials(
            world.deps,
            cost=reported_cost,
            overrides={call: failure for call in unreported_calls},
        )
        code = _cli_canned(
            world,
            deps,
            *SCOUT_HAIKU_ARGS,
            "--trials",
            str(SCOUT_TRIALS),
            "--max-cost",
            str(limit),
        )
        return code, _written(world)

    @pytest.mark.parametrize("kind", ["cli_error", "timeout"])
    def test_trials_with_no_reported_cost_are_charged_the_arms_per_trial_estimate(
        self, world, kind
    ):
        _, written = self._run_with_unreported_baseline_trials(world, kind)

        baseline = _arm_block(written, BASELINE_LABEL)
        unreported_trials = [
            trial
            for fixture in baseline["fixtures"]
            for trial in fixture["trials"]
            if not trial["cost_reported"]
        ]
        per_trial_estimate = BASELINE_TWO_ARM_ESTIMATE / ARM_RUN_CALLS
        assert len(unreported_trials) >= 1
        assert baseline["totals"]["unreported_trials_estimate_usd"] == pytest.approx(
            len(unreported_trials) * per_trial_estimate
        )

    @pytest.mark.parametrize("kind", ["cli_error", "timeout"])
    def test_charged_estimates_for_unreported_trials_stop_the_run_at_max_cost(
        self, world, kind
    ):
        code, written = self._run_with_unreported_baseline_trials(world, kind)

        completed = len(_outcomes(written, BASELINE_LABEL)) + len(
            _outcomes(written, CANDIDATE_LABEL)
        )
        assert code == 1
        assert written["abort_reason"] == "max-cost"
        assert completed < FULL_RUN_CALLS

    def test_cost_passing_max_cost_on_the_last_planned_trial_leaves_the_run_complete(
        self, world, capsys
    ):
        deps, trial_calls = _deps_with_canned_trials(world.deps)

        code = _cli_canned(
            world,
            deps,
            *CLEAN_FORM_ARGS,
            "--trials",
            "1",
            "--max-cost",
            str(1.5 * TRIAL_COST),
        )

        written = _written(world)
        assert code == 0
        assert len(trial_calls) == 2
        assert (written["status"], written["abort_reason"]) == ("complete", None)
        assert "run stopped early" not in capsys.readouterr().err


class TestSystemicFailureStop:
    @pytest.mark.parametrize("outcome", ["cli_error", "timeout"])
    def test_first_trial_ending_in_an_infra_outcome_stops_the_run_with_no_further_trial(
        self, world, outcome
    ):
        deps, _ = _deps_always_failing(world, outcome)

        code = _cli_canned(world, deps, *CLEAN_FORM_ARGS, "--trials", "5")

        written = _written(world)
        assert code == 1
        assert (written["status"], written["abort_reason"]) == (
            "incomplete",
            "infra-failure",
        )
        assert _outcomes(written, BASELINE_LABEL) == [outcome]
        assert _outcomes(written, CANDIDATE_LABEL) == []

    def test_candidate_whose_first_trial_fails_stops_the_run_after_one_trial_each(
        self, world
    ):
        deps, trial_calls = _deps_with_canned_trials(
            world.deps, overrides={1: CLI_FAILURE_RECORD}
        )

        code = _cli_canned(world, deps, *CLEAN_FORM_ARGS, "--trials", "5")

        written = _written(world)
        assert code == 1
        assert len(trial_calls) == 2
        assert _outcomes(written, BASELINE_LABEL) == ["pass"]
        assert _outcomes(written, CANDIDATE_LABEL) == ["cli_error"]

    @pytest.mark.parametrize(
        ("outcome", "cause"),
        [
            ("cli_error", "exit code 1: boom: auth failed"),
            ("timeout", "trial exceeded the time limit"),
        ],
    )
    def test_stderr_names_the_abort_reason_the_failing_trials_error_and_the_artifact(
        self, world, capsys, outcome, cause
    ):
        deps, _ = _deps_always_failing(world, outcome)

        _cli_canned(world, deps, *CLEAN_FORM_ARGS, "--trials", "5")

        err = capsys.readouterr().err
        assert (
            f"error: run stopped early (infra-failure): the baseline arm ended in "
            f"{outcome}. Likely cause: {cause}. Fix that and rerun"
        ) in err
        assert f"artifact written: {world.artifact_path}" in err

    def test_stderr_names_what_the_killed_process_printed_as_the_cause_of_a_timeout(
        self, world, capsys
    ):
        deps = _deps_timing_out(world, stderr="auth token expired")

        _cli_canned(world, deps, *CLEAN_FORM_ARGS, "--trials", "5")

        assert (
            "Likely cause: trial exceeded the time limit: auth token expired. "
            "Fix that and rerun"
        ) in capsys.readouterr().err

    def test_stderr_shows_the_cause_cut_at_the_cause_limit(self, world, capsys):
        long_stderr = "x" * (4 * CAUSE_LIMIT)
        failure = dataclasses.replace(CLI_FAILURE_RECORD, stderr=long_stderr)
        deps, _ = _deps_with_canned_trials(world.deps, default=failure)

        _cli_canned(world, deps, *CLEAN_FORM_ARGS, "--trials", "5")

        assert_cut_at_limit(capsys.readouterr().err, "exit code 1: ", "x")

    def test_terminal_control_sequences_in_the_cause_are_shown_escaped_not_executed(
        self, world, capsys
    ):
        hostile = "\x1b]0;pwned\x07\x1b[31mred\x1b[0m"
        failure = dataclasses.replace(CLI_FAILURE_RECORD, stderr=hostile)
        deps, _ = _deps_with_canned_trials(world.deps, default=failure)

        _cli_canned(world, deps, *CLEAN_FORM_ARGS, "--trials", "5")

        err = capsys.readouterr().err
        assert "\x1b" not in err and "\x07" not in err
        assert (
            "Likely cause: exit code 1: \\x1b]0;pwned\\x07\\x1b[31mred\\x1b[0m." in err
        )

    def test_three_consecutive_failures_in_the_baseline_arm_stop_the_run_on_the_third(
        self, world
    ):
        # Calls alternate baseline, candidate: the baseline fails on its trials 2, 3 and 4.
        deps, trial_calls = _deps_with_canned_trials(
            world.deps, overrides={call: CLI_FAILURE_RECORD for call in (2, 4, 6)}
        )

        code = _cli_canned(world, deps, *CLEAN_FORM_ARGS, "--trials", "5")

        written = _written(world)
        assert code == 1
        assert len(trial_calls) == 7
        assert written["abort_reason"] == "infra-failure"
        assert _outcomes(written, BASELINE_LABEL) == [
            "pass",
            "cli_error",
            "cli_error",
            "cli_error",
        ]
        assert _outcomes(written, CANDIDATE_LABEL) == ["pass", "pass", "pass"]

    def test_single_later_cli_error_does_not_stop_the_run(self, world):
        deps, trial_calls = _deps_with_canned_trials(
            world.deps, overrides={2: CLI_FAILURE_RECORD}
        )

        code = _cli_canned(world, deps, *CLEAN_FORM_ARGS, "--trials", "3")

        written = _written(world)
        assert code == 0
        assert len(trial_calls) == 6
        assert written["status"] == "complete"
        assert _outcomes(written, BASELINE_LABEL) == ["pass", "cli_error", "pass"]
