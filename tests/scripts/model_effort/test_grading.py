"""Grading a trial's verdict against the expected entry (model_effort.grading)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import ClassVar

import pytest
from ab_constants import GRADED_AGENT, GRADED_STEM, PASS_VERDICT
from model_effort import external, grading, paths
from model_effort.errors import UsageError


class TestGradeTrial:
    def test_verdict_matching_the_expected_entry_passes(self, graded_expected_dir):
        passed, messages = grading.grade_trial(
            GRADED_AGENT,
            GRADED_STEM,
            PASS_VERDICT,
            expected_dir=graded_expected_dir,
        )

        assert (passed, messages) == (True, [])

    def test_verdict_with_the_wrong_status_fails_with_a_status_message(
        self, graded_expected_dir
    ):
        wrong = {"status": "fail", "issues": [], "summary": ""}

        passed, messages = grading.grade_trial(
            GRADED_AGENT,
            GRADED_STEM,
            wrong,
            expected_dir=graded_expected_dir,
        )

        assert passed is False
        assert any("status" in message for message in messages)

    def test_only_the_named_expected_file_reaches_the_grader(self, graded_expected_dir):
        # A malformed sibling would crash the grader if it were copied too.
        (graded_expected_dir / "two.json").write_text("{not json", encoding="utf-8")

        passed, _ = grading.grade_trial(
            GRADED_AGENT,
            GRADED_STEM,
            PASS_VERDICT,
            expected_dir=graded_expected_dir,
        )

        assert passed is True

    def test_agent_absent_from_the_expected_entry_fails_with_a_message(
        self, graded_expected_dir
    ):
        passed, messages = grading.grade_trial(
            "no-such-agent",
            GRADED_STEM,
            {},
            expected_dir=graded_expected_dir,
        )

        assert passed is False
        assert messages

    @pytest.mark.parametrize(
        "error",
        [TypeError, KeyError, AttributeError, ValueError],
        ids=lambda e: e.__name__,
    )
    def test_agent_answer_shaped_errors_from_the_grader_fail_the_trial_naming_the_error(
        self, graded_expected_dir, monkeypatch, error
    ):
        answer = {"odd": "shape"}
        real_grading = external.eval_grade().run_grading

        def raising_grader(**kwargs):
            if kwargs["actuals"][GRADED_STEM]["agents"][GRADED_AGENT] == answer:
                raise error("bad shape")
            return real_grading(**kwargs)

        monkeypatch.setattr(external.eval_grade(), "run_grading", raising_grader)

        passed, messages = grading.grade_trial(
            GRADED_AGENT,
            GRADED_STEM,
            answer,
            expected_dir=graded_expected_dir,
        )

        assert passed is False
        assert len(messages) == 1 and error.__name__ in messages[0]

    def test_other_errors_from_the_grader_propagate(
        self, graded_expected_dir, monkeypatch
    ):
        def failing_grader(**_kwargs):
            raise OSError("disk gone")

        monkeypatch.setattr(external.eval_grade(), "run_grading", failing_grader)

        with pytest.raises(OSError, match="disk gone"):
            grading.grade_trial(
                GRADED_AGENT,
                GRADED_STEM,
                {},
                expected_dir=graded_expected_dir,
            )

    @pytest.mark.parametrize("error", [OSError, ValueError], ids=lambda e: e.__name__)
    def test_errors_while_staging_the_expected_entry_propagate(
        self, graded_expected_dir, monkeypatch, error
    ):
        def failing_copy(*_args, **_kwargs):
            raise error("cannot stage")

        monkeypatch.setattr(grading, "shutil", SimpleNamespace(copy2=failing_copy))

        with pytest.raises(error, match="cannot stage"):
            grading.grade_trial(
                GRADED_AGENT,
                GRADED_STEM,
                PASS_VERDICT,
                expected_dir=graded_expected_dir,
            )

    def test_grading_leaves_no_temp_dir_behind(
        self, graded_expected_dir, tmp_path, monkeypatch
    ):
        scratch = tmp_path / "scratch"
        scratch.mkdir()
        monkeypatch.setattr(grading.tempfile, "tempdir", str(scratch))

        grading.grade_trial(
            GRADED_AGENT,
            GRADED_STEM,
            PASS_VERDICT,
            expected_dir=graded_expected_dir,
        )

        assert list(scratch.iterdir()) == []


class TestUpstreamGraderDrift:
    """A grader that no longer fits the call is the harness's fault, never a failed trial."""

    def test_a_renamed_parameter_is_a_contract_error_not_a_failed_trial(
        self, graded_expected_dir, monkeypatch
    ):
        def renamed(expected_directory, actuals, baseline, only=None):
            raise AssertionError("must not be called with the old keywords")

        monkeypatch.setattr(external.eval_grade(), "run_grading", renamed)

        with pytest.raises(external.ExternalContractError, match="run_grading"):
            grading.grade_trial(
                GRADED_AGENT,
                GRADED_STEM,
                PASS_VERDICT,
                expected_dir=graded_expected_dir,
            )

    @pytest.mark.parametrize(
        "returned",
        [None, [("pair", True, [])], (["pair"], None), ([("pair", True)], None)],
        ids=["none", "no-baseline-slot", "short-row", "short-triple"],
    )
    def test_a_changed_return_shape_is_a_contract_error_not_a_failed_trial(
        self, graded_expected_dir, monkeypatch, returned
    ):
        monkeypatch.setattr(
            external.eval_grade(), "run_grading", lambda **_kwargs: returned
        )

        with pytest.raises(external.ExternalContractError, match="run_grading"):
            grading.grade_trial(
                GRADED_AGENT,
                GRADED_STEM,
                PASS_VERDICT,
                expected_dir=graded_expected_dir,
            )


class TestShippedExpectedEntrySmoke:
    def test_clean_form_verdict_grades_as_pass_against_the_shipped_entry(self):
        passed, messages = grading.grade_trial(
            "a11y-review",
            "a11y-clean-form",
            PASS_VERDICT,
            paths.EXPECTED_DIR,
        )

        assert (passed, messages) == (True, [])


def _write_entry(expected_dir, stem, agents: dict) -> None:
    entry = {"fixture": stem, "applicableAgents": list(agents), "agents": agents}
    (expected_dir / f"{stem}.json").write_text(json.dumps(entry), encoding="utf-8")


class TestMalformedExpectedEntry:
    """An expected entry the grader cannot use is a data fault, never the agent's failure."""

    MALFORMED: ClassVar[dict] = {"expectedStatus": "fail", "issueCount": 3}

    def test_a_malformed_entry_is_refused_naming_the_fixture_and_agent(
        self, expected_dir
    ):
        _write_entry(expected_dir, GRADED_STEM, {GRADED_AGENT: self.MALFORMED})

        with pytest.raises(UsageError) as excinfo:
            grading.check_expected_entries(GRADED_AGENT, [GRADED_STEM], expected_dir)

        message = str(excinfo.value)
        assert f"{GRADED_STEM}.json" in message and GRADED_AGENT in message

    def test_a_well_formed_entry_is_accepted(self, graded_expected_dir):
        grading.check_expected_entries(GRADED_AGENT, [GRADED_STEM], graded_expected_dir)

    def test_another_agents_malformed_entry_is_not_this_agents_fault(
        self, expected_dir
    ):
        _write_entry(
            expected_dir,
            GRADED_STEM,
            {GRADED_AGENT: {"expectedStatus": "pass"}, "other": self.MALFORMED},
        )

        grading.check_expected_entries(GRADED_AGENT, [GRADED_STEM], expected_dir)

    def test_grading_against_a_malformed_entry_is_a_harness_fault_not_a_failed_trial(
        self, expected_dir
    ):
        _write_entry(expected_dir, GRADED_STEM, {GRADED_AGENT: self.MALFORMED})

        with pytest.raises(grading.MalformedExpectedEntryError, match=GRADED_STEM):
            grading.grade_trial(
                GRADED_AGENT,
                GRADED_STEM,
                PASS_VERDICT,
                expected_dir=expected_dir,
            )

    def test_an_answer_the_grader_cannot_read_still_fails_the_trial(
        self, expected_dir
    ):
        _write_entry(
            expected_dir, GRADED_STEM, {GRADED_AGENT: {"issueCount": {"max": 0}}}
        )

        passed, messages = grading.grade_trial(
            GRADED_AGENT,
            GRADED_STEM,
            {"status": "pass", "issues": 7},
            expected_dir=expected_dir,
        )

        assert passed is False
        assert "TypeError" in messages[0]

    def test_every_shipped_entry_passes_the_check(self):
        default = paths.EvalPaths.default()
        for entry_file in sorted(default.expected_dir.glob("*.json")):
            agents = json.loads(entry_file.read_text(encoding="utf-8")).get("agents", {})
            for agent in agents:
                grading.check_expected_entries(
                    agent, [entry_file.stem], default.expected_dir
                )
