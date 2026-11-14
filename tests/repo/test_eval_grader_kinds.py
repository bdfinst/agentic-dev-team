"""The graders for agents whose output is not a review verdict: planted finding IDs,
dispatch sets, sandbox test results and recorded rubric judgements.

Each is a pure function of an expected-entry block and a recorded output, so these
tests call them directly.
"""

from __future__ import annotations

import sys
from typing import ClassVar

import pytest

from _repo_root import REPO_ROOT

if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from eval_graders import get_grader, registered_graders
from eval_graders.dispatch_set import grade_dispatch_set
from eval_graders.finding_ids import grade_finding_ids
from eval_graders.rubric import grade_rubric
from eval_graders.tests_pass import grade_tests_pass

PLAN_SPEC = {
    "statusField": "verdict",
    "expectedStatus": "needs-revision",
    "findingFields": ["criteria_issues", "step_issues"],
    "expectedFindingIds": [
        {
            "id": "weasel-ac2",
            "anyOf": ["appropriately", "AC2"],
            "severityAnyOf": ["blocker"],
        },
        {"id": "vague-step", "anyOf": ["vague test"]},
    ],
    "maxFindings": 3,
}


def _plan_output(**overrides) -> dict:
    output = {
        "verdict": "needs-revision",
        "criteria_issues": [
            {
                "criterion": "AC2",
                "issue": "'appropriately' is not verifiable",
                "severity": "blocker",
            }
        ],
        "step_issues": [{"step": "2.1", "issue": "Vague test description"}],
    }
    return {**output, **overrides}


@pytest.mark.parametrize(
    "name", ["finding_ids", "dispatch_set", "tests_pass", "rubric"]
)
def test_each_new_grader_is_registered(name):
    assert name in registered_graders()
    assert get_grader(name) is not None


class TestFindingIds:
    def test_every_planted_id_matched_passes(self):
        assert grade_finding_ids(PLAN_SPEC, _plan_output()) == []

    def test_an_unmatched_id_fails_naming_it(self):
        output = _plan_output(step_issues=[])

        assert grade_finding_ids(PLAN_SPEC, output) == [
            "expectedFindingIds: no finding matches 'vague-step' (keywords ['vague test'])"
        ]

    def test_a_keyword_match_at_the_wrong_severity_does_not_count(self):
        output = _plan_output(
            criteria_issues=[{"criterion": "AC2", "issue": "x", "severity": "warning"}]
        )

        assert any("weasel-ac2" in m for m in grade_finding_ids(PLAN_SPEC, output))

    def test_a_wrong_verdict_fails(self):
        output = _plan_output(verdict="approve")

        assert grade_finding_ids(PLAN_SPEC, output) == [
            "verdict: expected 'needs-revision', got 'approve'"
        ]

    def test_findings_over_the_cap_fail(self):
        extra = [{"step": str(n), "issue": "vague test"} for n in range(3)]

        fails = grade_finding_ids(PLAN_SPEC, _plan_output(step_issues=extra))

        assert fails == ["maxFindings: expected at most 3, got 4"]

    def test_a_where_filter_counts_only_items_with_an_allowed_value(self):
        spec = {
            "findingFields": [
                {"field": "criterionResults", "where": {"result": ["missing"]}}
            ],
            "expectedFindingIds": [],
            "maxFindings": 0,
        }
        covered = {"criterionResults": [{"criterion": "AC1", "result": "covered"}]}
        missing = {"criterionResults": [{"criterion": "AC1", "result": "missing"}]}

        assert grade_finding_ids(spec, covered) == []
        assert grade_finding_ids(spec, missing) == [
            "maxFindings: expected at most 0, got 1"
        ]

    def test_a_clean_fixture_fails_on_any_blocker(self):
        spec = {
            "findingFields": ["issues"],
            "expectedFindingIds": [],
            "maxBySeverity": {"blocker": 0},
        }
        output = {"issues": [{"description": "x", "severity": "blocker"}]}

        assert grade_finding_ids(spec, output) == [
            "maxBySeverity.blocker: expected at most 0, got 1"
        ]


class TestDispatchSet:
    SPEC: ClassVar[dict] = {"dispatch": {"include": ["architect"], "exclude": ["security-review"]}}

    def test_plugin_qualified_names_count_as_bare_names(self):
        assert (
            grade_dispatch_set(self.SPEC, {"dispatched": ["dev-team:architect"]}) == []
        )

    def test_a_missing_or_forbidden_dispatch_fails(self):
        fails = grade_dispatch_set(self.SPEC, {"dispatched": ["security-review"]})

        assert fails == [
            "dispatch: expected architect to be dispatched",
            "dispatch: security-review must not be dispatched",
        ]

    def test_an_exact_set_rejects_extra_dispatches(self):
        spec = {"dispatch": {"include": [], "exact": True}}

        assert grade_dispatch_set(spec, {"dispatched": ["test-review"]}) == [
            "dispatch: unexpected dispatch of test-review"
        ]

    def test_the_status_check_reads_the_agents_json_output(self):
        spec = {"dispatch": {"include": [], "exact": True}, "expectedStatus": "skip"}

        assert (
            grade_dispatch_set(spec, {"dispatched": [], "output": {"status": "skip"}})
            == []
        )
        assert grade_dispatch_set(spec, {"dispatched": [], "output": {}}) == [
            "status: expected 'skip', got None"
        ]


class TestTestsPass:
    SPEC: ClassVar[dict] = {"testCommands": ["{python} -m unittest"]}

    def test_every_command_exiting_zero_passes(self):
        actual = {"results": [{"command": "{python} -m unittest", "exit_code": 0}]}

        assert grade_tests_pass(self.SPEC, actual) == []

    def test_a_failing_command_fails_with_its_exit_code_and_reason(self):
        actual = {
            "results": [
                {
                    "command": "{python} -m unittest",
                    "exit_code": 1,
                    "stderr_first_line": "FAILED",
                }
            ]
        }

        assert grade_tests_pass(self.SPEC, actual) == [
            "tests_pass: command '{python} -m unittest' exited 1 — FAILED"
        ]

    def test_no_recorded_result_fails(self):
        assert grade_tests_pass(self.SPEC, {"results": []}) == [
            "tests_pass: no result recorded for command '{python} -m unittest'"
        ]


class TestRubric:
    SPEC: ClassVar[dict] = {"rubricPoints": [{"id": "picks-queue", "requirement": "Picks the queue."}]}

    def _actual(self, *verdicts: dict) -> dict:
        return {"criterionIds": ["commits"], "judgement": {"criteria": list(verdicts)}}

    def test_every_criterion_and_point_met_passes(self):
        actual = self._actual(
            {"id": "commits", "met": True}, {"id": "picks-queue", "met": True}
        )

        assert grade_rubric(self.SPEC, actual) == []

    def test_an_unmet_criterion_fails_with_the_judges_reason(self):
        actual = self._actual(
            {"id": "commits", "met": False, "reason": "hedges"},
            {"id": "picks-queue", "met": True},
        )

        assert grade_rubric(self.SPEC, actual) == ["rubric: 'commits' not met — hedges"]

    def test_a_criterion_the_judge_skipped_counts_as_not_met(self):
        actual = self._actual({"id": "commits", "met": True})

        assert grade_rubric(self.SPEC, actual) == [
            "rubric: judge gave no verdict for 'picks-queue'"
        ]

    def test_a_truthy_non_boolean_met_is_not_met(self):
        actual = self._actual(
            {"id": "commits", "met": "yes"}, {"id": "picks-queue", "met": True}
        )

        assert grade_rubric(self.SPEC, actual) == ["rubric: 'commits' not met"]
