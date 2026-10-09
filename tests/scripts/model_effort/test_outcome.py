"""Resolving a finished trial into an outcome (model_effort.outcome)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from _model_effort_support import (
    CAUSE_LIMIT,
    ENABLED,
    GRADED_AGENT,
    GRADED_STEM,
    HAIKU_MODEL_ID,
    PASS_VERDICT,
    TRIAL_COST,
    TRUNCATED_OUTER_OBJECT,
    StubClaude,
    _config,
    _eval_paths,
    _expected_session_config,
    _fixture_text,
    _init_event,
    _make_file_fixture,
    _result_event,
    _stream,
    _tool_use_event,
)
from model_effort import grading, outcome, process_record, runner, transcript
from model_effort.outcome import Outcome


def _record(
    exit_code=0, stdout="", stderr="", timed_out=False, cwd=None
) -> process_record.TrialProcessRecord:
    return process_record.TrialProcessRecord(
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        cwd=cwd,
    )


def _resolve(stdout: str, grader=None, **record_fields) -> outcome.TrialResult:
    record = _record(stdout=stdout, **record_fields)
    parsed = transcript.parse_stream(stdout)
    grader = grader or (lambda agent_json: (True, []))
    return outcome.resolve_outcome(record, parsed, ENABLED, grader)


@pytest.fixture
def real_grader(graded_expected_dir):
    def grade(agent_json: dict) -> tuple[bool, list[str]]:
        return grading.grade_trial(
            GRADED_AGENT,
            GRADED_STEM,
            agent_json,
            eval_paths=_eval_paths(expected_dir=graded_expected_dir),
        )

    return grade


def _verdict_stream(verdict: dict, *tool_names: str) -> str:
    events = [_tool_use_event(*tool_names)] if tool_names else []
    return _stream(*events, _result_event(json.dumps(verdict)))


class TestOutcomeEnum:
    def test_outcomes_are_declared_in_precedence_order(self):
        assert [member.value for member in Outcome] == [
            "timeout",
            "cli_error",
            "tool_violation",
            "parse_failure",
            "graded_fail",
            "pass",
        ]

    def test_infrastructure_outcomes_are_cli_error_and_timeout(self):
        assert outcome.INFRA_OUTCOMES == {Outcome.CLI_ERROR, Outcome.TIMEOUT}


class TestTrialOutcomes:
    def test_json_satisfying_the_expected_entry_is_pass(self, real_grader):
        result = _resolve(_verdict_stream(PASS_VERDICT), real_grader)

        assert result.outcome == Outcome.PASS
        assert result.error is None
        assert result.grader_messages == ()

    def test_json_with_the_wrong_status_is_graded_fail_with_grader_messages(
        self, real_grader
    ):
        wrong = {"status": "fail", "issues": [], "summary": ""}

        result = _resolve(_verdict_stream(wrong), real_grader)

        assert result.outcome == Outcome.GRADED_FAIL
        assert any("status" in m for m in result.grader_messages)

    @pytest.mark.parametrize(
        ("malformed", "error_type"),
        [({"issues": ["text"]}, "AttributeError"), ({"issues": 3}, "TypeError")],
        ids=["issues-as-strings", "issues-as-number"],
    )
    def test_json_shaped_so_the_real_grader_raises_is_graded_fail_naming_the_error(
        self, real_grader, malformed, error_type
    ):
        result = _resolve(_verdict_stream(malformed), real_grader)

        assert result.outcome == Outcome.GRADED_FAIL
        assert len(result.grader_messages) == 1
        assert error_type in result.grader_messages[0]

    def test_error_raised_by_the_grader_is_not_a_verdict_and_propagates(self):
        def failing_grader(_agent_json):
            raise OSError("grading disk gone")

        with pytest.raises(OSError, match="grading disk gone"):
            _resolve(_verdict_stream(PASS_VERDICT), failing_grader)

    def test_text_with_no_json_object_is_parse_failure(self):
        result = _resolve(_stream(_result_event("I found nothing to report.")))

        assert result.outcome == Outcome.PARSE_FAILURE
        assert result.error

    def test_truncated_outer_object_is_parse_failure_not_its_inner_object(self):
        result = _resolve(_stream(_result_event(TRUNCATED_OUTER_OBJECT)))

        assert result.outcome == Outcome.PARSE_FAILURE

    def test_call_to_a_tool_outside_the_enabled_set_is_tool_violation_naming_it(self):
        result = _resolve(_verdict_stream(PASS_VERDICT, "Read", "Bash"))

        assert result.outcome == Outcome.TOOL_VIOLATION
        assert "Bash" in result.error
        assert "Read" not in result.error

    def test_webfetch_call_with_passing_json_is_tool_violation(self, real_grader):
        result = _resolve(_verdict_stream(PASS_VERDICT, "WebFetch"), real_grader)

        assert result.outcome == Outcome.TOOL_VIOLATION
        assert "WebFetch" in result.error

    @pytest.mark.parametrize("tool_name", ["Bash", "WebFetch"])
    def test_tool_violation_outranks_parse_failure(self, tool_name):
        stdout = _stream(_tool_use_event(tool_name), _result_event("no json here"))

        result = _resolve(stdout)

        assert result.outcome == Outcome.TOOL_VIOLATION

    def test_non_zero_exit_is_cli_error_carrying_stderr(self):
        result = _resolve(
            _verdict_stream(PASS_VERDICT), exit_code=1, stderr="model not found"
        )

        assert result.outcome == Outcome.CLI_ERROR
        assert "model not found" in result.error

    def test_webfetch_call_with_non_zero_exit_is_cli_error(self):
        result = _resolve(_verdict_stream(PASS_VERDICT, "WebFetch"), exit_code=1)

        assert result.outcome == Outcome.CLI_ERROR

    def test_exit_zero_with_no_result_event_is_cli_error(self):
        result = _resolve(_stream(_tool_use_event("Read")))

        assert result.outcome == Outcome.CLI_ERROR
        assert "result" in result.error

    def test_result_event_flagged_is_error_is_cli_error_even_with_exit_zero(self):
        stdout = _stream(_result_event("model gone", is_error=True))

        result = _resolve(stdout)

        assert result.outcome == Outcome.CLI_ERROR
        assert "model gone" in result.error

    def test_timed_out_run_is_timeout_even_with_other_failures(self):
        result = _resolve(
            _stream(_tool_use_event("WebFetch")),
            exit_code=None,
            timed_out=True,
        )

        assert result.outcome == Outcome.TIMEOUT

    def test_timeout_error_is_the_time_limit_notice_when_no_stderr_was_left(self):
        result = _resolve("", exit_code=None, timed_out=True, stderr="  \n")

        assert result.error == "trial exceeded the time limit"

    def test_timeout_error_carries_the_partial_stderr_the_killed_process_left(self):
        result = _resolve(
            "", exit_code=None, timed_out=True, stderr="  rate limited, retrying\n"
        )

        assert result.error == "trial exceeded the time limit: rate limited, retrying"

    def test_timeout_error_stderr_has_the_staged_directory_scrubbed_and_is_capped(self):
        staged = Path(tempfile.gettempdir()) / f"{runner.TEMP_DIR_PREFIX}abc123"
        result = _resolve(
            "",
            exit_code=None,
            timed_out=True,
            stderr=f"stuck reading {staged}/form.html " + "x" * (4 * CAUSE_LIMIT),
            cwd=staged,
        )

        assert "<staged>/form.html" in result.error
        assert str(staged) not in result.error
        assert len(result.error) == CAUSE_LIMIT

    def test_recorded_successful_run_resolves_to_pass_with_a_passing_grader(self):
        result = _resolve(_fixture_text("pass-readonly.jsonl"))

        assert result.outcome == Outcome.PASS

    def test_recorded_bad_model_run_resolves_to_cli_error_carrying_stderr(self):
        result = _resolve(
            _fixture_text("bad-model.jsonl"),
            exit_code=1,
            stderr=_fixture_text("bad-model.stderr.txt"),
        )

        assert result.outcome == Outcome.CLI_ERROR
        assert "unrecognized_model" in result.error

    @pytest.mark.parametrize(
        ("stdout", "record_fields"),
        [
            pytest.param(
                _verdict_stream(PASS_VERDICT, "WebFetch"), {}, id="tool-violation"
            ),
            pytest.param(_stream(_result_event("no json")), {}, id="parse-failure"),
            pytest.param(
                _verdict_stream(PASS_VERDICT), {"exit_code": 1}, id="cli-error"
            ),
            pytest.param(
                _verdict_stream(PASS_VERDICT),
                {"exit_code": None, "timed_out": True},
                id="timeout",
            ),
        ],
    )
    def test_grader_is_not_called_when_an_earlier_check_decides_the_outcome(
        self, stdout, record_fields
    ):
        calls = []

        def spy(agent_json):
            calls.append(agent_json)
            return True, []

        _resolve(stdout, spy, **record_fields)

        assert calls == []

    def test_cost_and_model_id_come_from_the_transcript(self):
        result = _resolve(_verdict_stream(PASS_VERDICT))

        assert result.reported_cost_usd == pytest.approx(TRIAL_COST)
        assert result.model_id == HAIKU_MODEL_ID
        assert result.model_id_note is None

    def test_cost_is_kept_for_a_failed_trial(self):
        result = _resolve(_verdict_stream(PASS_VERDICT, "WebFetch"))

        assert result.reported_cost_usd == pytest.approx(TRIAL_COST)

    def test_trial_with_a_reported_cost_is_marked_reported(self):
        assert _resolve(_verdict_stream(PASS_VERDICT)).cost_reported is True

    def test_trial_with_no_result_event_has_zero_cost_marked_unreported(self):
        result = _resolve(_stream(_tool_use_event("Read")), exit_code=1)

        assert (result.reported_cost_usd, result.cost_reported) == (0.0, False)

    def test_trial_with_a_non_finite_cost_has_zero_cost_marked_unreported(self):
        stdout = _stream(
            _result_event(json.dumps(PASS_VERDICT), total_cost_usd=float("nan"))
        )

        result = _resolve(stdout)

        assert (result.reported_cost_usd, result.cost_reported) == (0.0, False)

    def test_session_config_comes_from_the_transcript_init_event(self):
        stdout = _stream(_init_event(), _result_event(json.dumps(PASS_VERDICT)))

        result = _resolve(stdout)

        assert result.session_config == _expected_session_config(HAIKU_MODEL_ID)


class TestErrorTextIsScrubbed:
    def test_the_staged_directory_in_a_cli_error_becomes_a_placeholder(self):
        staged = Path(tempfile.mkdtemp(prefix=runner.TEMP_DIR_PREFIX))
        try:
            result = _resolve(
                "",
                exit_code=1,
                stderr=f"cannot read {staged}/form.html",
                cwd=staged,
            )
        finally:
            staged.rmdir()

        assert "<staged>/form.html" in result.error
        assert str(staged) not in result.error

    def test_a_real_failed_trial_reports_no_part_of_its_temp_directory(
        self, stub_dir, fixture_root
    ):
        stub = StubClaude(stub_dir, exit_code=1, stderr_cwd=True)
        fixture = _make_file_fixture(fixture_root, "a.txt", "a")

        record = runner.run_trial(fixture, _config(stub))
        result = outcome.resolve_outcome(
            record,
            transcript.parse_stream(record.stdout),
            ENABLED,
            lambda agent_json: (True, []),
        )

        ran_in = stub.calls[0]["cwd"]
        assert "<staged>/form.html" in result.error
        assert ran_in not in result.error
        assert str(record.cwd) not in result.error


class TestMessageCaps:
    def test_error_is_capped_at_the_cause_limit(self):
        errored = _resolve(_verdict_stream(PASS_VERDICT), exit_code=1, stderr="e" * 900)

        assert len(errored.error) == CAUSE_LIMIT

    def test_a_single_long_grader_message_is_capped_at_the_cause_limit(self):
        long_message = "m" * (2 * CAUSE_LIMIT)
        graded = _resolve(
            _verdict_stream(PASS_VERDICT), lambda j: (False, [long_message])
        )

        assert [len(m) for m in graded.grader_messages] == [CAUSE_LIMIT]

    def test_combined_grader_messages_are_capped_at_the_cause_limit(self):
        first_length = CAUSE_LIMIT * 3 // 5
        messages = ["a" * first_length, "b" * CAUSE_LIMIT, "c" * CAUSE_LIMIT]

        graded = _resolve(_verdict_stream(PASS_VERDICT), lambda j: (False, messages))

        assert graded.grader_messages == (
            "a" * first_length,
            "b" * (CAUSE_LIMIT - first_length),
        )

    def test_messages_that_fit_the_cap_are_kept_whole(self):
        messages = ["a" * 100, "b" * 100]

        graded = _resolve(_verdict_stream(PASS_VERDICT), lambda j: (False, messages))

        assert graded.grader_messages == tuple(messages)
