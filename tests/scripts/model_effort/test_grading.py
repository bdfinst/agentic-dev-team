"""Grading a trial's verdict against the expected entry (model_effort.grading)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from _model_effort_support import GRADED_AGENT, GRADED_STEM, PASS_VERDICT, _eval_paths
from model_effort import external, grading, paths


class TestGradeTrial:
    def test_verdict_matching_the_expected_entry_passes(self, graded_expected_dir):
        passed, messages = grading.grade_trial(
            GRADED_AGENT,
            GRADED_STEM,
            PASS_VERDICT,
            eval_paths=_eval_paths(expected_dir=graded_expected_dir),
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
            eval_paths=_eval_paths(expected_dir=graded_expected_dir),
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
            eval_paths=_eval_paths(expected_dir=graded_expected_dir),
        )

        assert passed is True

    def test_agent_absent_from_the_expected_entry_fails_with_a_message(
        self, graded_expected_dir
    ):
        passed, messages = grading.grade_trial(
            "no-such-agent",
            GRADED_STEM,
            {},
            eval_paths=_eval_paths(expected_dir=graded_expected_dir),
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
        def raising_grader(**_kwargs):
            raise error("bad shape")

        monkeypatch.setattr(external.eval_grade(), "run_grading", raising_grader)

        passed, messages = grading.grade_trial(
            GRADED_AGENT,
            GRADED_STEM,
            {},
            eval_paths=_eval_paths(expected_dir=graded_expected_dir),
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
                eval_paths=_eval_paths(expected_dir=graded_expected_dir),
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
                eval_paths=_eval_paths(expected_dir=graded_expected_dir),
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
            eval_paths=_eval_paths(expected_dir=graded_expected_dir),
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
                eval_paths=_eval_paths(expected_dir=graded_expected_dir),
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
                eval_paths=_eval_paths(expected_dir=graded_expected_dir),
            )


class TestShippedExpectedEntrySmoke:
    def test_clean_form_verdict_grades_as_pass_against_the_shipped_entry(self):
        passed, messages = grading.grade_trial(
            "a11y-review",
            "a11y-clean-form",
            PASS_VERDICT,
            paths.EvalPaths.default(),
        )

        assert (passed, messages) == (True, [])
