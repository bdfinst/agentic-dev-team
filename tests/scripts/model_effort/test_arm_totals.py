"""Per-arm totals (model_effort.arm_totals)."""

from __future__ import annotations

import pytest
from _model_effort_support import (
    ARM_ESTIMATE,
    READ_ONLY_PROFILE,
    TRIAL_COST,
    _arm_run,
    _built_arm,
    _metadata,
    _run_estimate,
    _trial_result,
)
from model_effort import arm_totals, artifact
from model_effort.arm import CANDIDATE_LABEL
from model_effort.outcome import Outcome


class TestComputeArmTotals:
    def _totals(self, results, expected_clean=False, total_trials_per_arm=3):
        run = _arm_run(CANDIDATE_LABEL, results, expected_clean)
        return arm_totals.compute_arm_totals(run, _run_estimate(total_trials_per_arm))

    def test_totals_carry_every_figure_the_artifact_and_summary_show(self):
        totals = self._totals(
            [
                _trial_result(Outcome.PASS),
                _trial_result(Outcome.GRADED_FAIL),
                _trial_result(Outcome.TIMEOUT, cost=0.0, cost_reported=False),
            ],
            expected_clean=True,
        )

        assert totals == arm_totals.ArmTotals(
            label=CANDIDATE_LABEL,
            outcome_counts={
                Outcome.TIMEOUT: 1,
                Outcome.CLI_ERROR: 0,
                Outcome.TOOL_VIOLATION: 0,
                Outcome.PARSE_FAILURE: 0,
                Outcome.GRADED_FAIL: 1,
                Outcome.PASS: 1,
            },
            clean_fixture_false_positives=1,
            actual_cost_usd=pytest.approx(TRIAL_COST * 2),
            unreported_trials_estimate_usd=pytest.approx(ARM_ESTIMATE),
            estimated_cost_usd=pytest.approx(3 * ARM_ESTIMATE),
        )

    def test_outcome_counts_follow_the_outcome_precedence_order(self):
        totals = self._totals([_trial_result(Outcome.PASS)])

        assert list(totals.outcome_counts) == list(Outcome)

    def test_artifact_serializes_the_same_totals_the_summary_is_given(self):
        run = _arm_run(
            CANDIDATE_LABEL,
            [_trial_result(Outcome.GRADED_FAIL), _trial_result(Outcome.PASS)],
            expected_clean=True,
        )
        totals = arm_totals.compute_arm_totals(run, _run_estimate())

        built = artifact.build_artifact(
            _metadata(), [run], _run_estimate(), READ_ONLY_PROFILE, None
        )

        assert built["arms"][0]["totals"] == {
            **{
                outcome.value: count for outcome, count in totals.outcome_counts.items()
            },
            "clean_fixture_false_positives": totals.clean_fixture_false_positives,
            "actual_cost_usd": totals.actual_cost_usd,
            "unreported_trials_estimate_usd": totals.unreported_trials_estimate_usd,
        }
        assert built["arms"][0]["estimated_cost_usd"] == totals.estimated_cost_usd


class TestArmTotals:
    def test_every_outcome_is_counted_with_zeros_included(self):
        arm = _built_arm(
            [_trial_result(Outcome.PASS), _trial_result(Outcome.PARSE_FAILURE)]
        )

        assert arm["totals"] == {
            "pass": 1,
            "graded_fail": 0,
            "parse_failure": 1,
            "tool_violation": 0,
            "cli_error": 0,
            "timeout": 0,
            "clean_fixture_false_positives": 0,
            "actual_cost_usd": pytest.approx(0.02),
            "unreported_trials_estimate_usd": 0.0,
        }

    def test_trial_without_a_reported_cost_is_flagged_and_charged_the_arms_per_trial_estimate(
        self,
    ):
        arm = _built_arm(
            [
                _trial_result(Outcome.PASS),
                _trial_result(Outcome.TIMEOUT, cost=0.0, cost_reported=False),
                _trial_result(Outcome.CLI_ERROR, cost=0.0, cost_reported=False),
            ],
            total_trials_per_arm=3,
        )

        trials = arm["fixtures"][0]["trials"]
        assert [trial["cost_reported"] for trial in trials] == [True, False, False]
        assert arm["totals"]["actual_cost_usd"] == pytest.approx(TRIAL_COST)
        assert arm["totals"]["unreported_trials_estimate_usd"] == pytest.approx(
            2 * ARM_ESTIMATE
        )

    def test_arm_records_its_estimated_cost_from_the_run_estimate(self):
        arm = _built_arm([_trial_result(Outcome.PASS)], total_trials_per_arm=4)

        assert arm["estimated_cost_usd"] == pytest.approx(4 * ARM_ESTIMATE)

    def test_clean_fixture_false_positives_count_only_graded_fails_on_clean_fixtures(
        self,
    ):
        arm = _built_arm(
            [
                _trial_result(Outcome.PASS),
                _trial_result(Outcome.GRADED_FAIL),
                _trial_result(Outcome.GRADED_FAIL),
                _trial_result(Outcome.CLI_ERROR),
                _trial_result(Outcome.TIMEOUT),
                _trial_result(Outcome.PARSE_FAILURE),
                _trial_result(Outcome.TOOL_VIOLATION),
            ],
            expected_clean=True,
        )

        assert arm["totals"]["clean_fixture_false_positives"] == 2

    def test_non_clean_fixtures_never_count_as_clean_fixture_false_positives(self):
        arm = _built_arm([_trial_result(Outcome.GRADED_FAIL)], expected_clean=False)

        assert arm["totals"]["clean_fixture_false_positives"] == 0

    def test_model_id_is_reported_when_every_reporting_trial_agrees(self):
        arm = _built_arm(
            [
                _trial_result(Outcome.PASS, model_id="m-1"),
                _trial_result(Outcome.CLI_ERROR, note="no result"),
            ]
        )

        assert (arm["model_id"], arm["model_id_note"]) == ("m-1", None)

    def test_conflicting_model_ids_yield_null_with_a_note_naming_them(self):
        arm = _built_arm(
            [
                _trial_result(Outcome.PASS, model_id="m-1"),
                _trial_result(Outcome.PASS, model_id="m-2"),
            ]
        )

        assert arm["model_id"] is None
        assert "m-1" in arm["model_id_note"] and "m-2" in arm["model_id_note"]

    def test_no_reported_model_id_yields_null_with_the_trial_note(self):
        arm = _built_arm([_trial_result(Outcome.CLI_ERROR, note="no result event")])

        assert (arm["model_id"], arm["model_id_note"]) == (None, "no result event")
