"""Transcript parsing (model_effort.transcript). The recorded transcripts are the harness's parser fixtures."""

from __future__ import annotations

import json
import time

import pytest
from _model_effort_support import (
    HAIKU_MODEL_ID,
    TRANSCRIPT_FIXTURES,
    TRUNCATED_OUTER_OBJECT,
    _expected_session_config,
    _fixture_text,
    _init_event,
    _result_event,
    _stream,
    _tool_use_event,
)
from model_effort import transcript


def _read_transcript(name: str) -> transcript.ParsedTranscript:
    return transcript.parse_stream(_fixture_text(f"{name}.jsonl"))


class TestParseStream:
    def test_real_read_only_run_yields_result_cost_model_and_tool_names(self):
        parsed = _read_transcript("pass-readonly")

        assert parsed.has_result is True
        assert parsed.is_error is False
        assert parsed.result_text == '{"status": "ok", "knowledge_read": true}'
        assert parsed.cost_usd == pytest.approx(0.00041539)
        assert parsed.model_id == HAIKU_MODEL_ID
        assert parsed.model_id_note is None
        assert parsed.called_tool_names == ("Read", "Read")

    def test_real_run_with_a_denied_read_shows_the_attempt_and_the_denial(self):
        parsed = _read_transcript("read-outside-denied")

        assert parsed.has_result is True
        assert parsed.called_tool_names == ("Read",)
        assert parsed.permission_denial_count == 1

    def test_real_run_with_allowed_reads_has_no_permission_denials(self):
        assert _read_transcript("pass-readonly").permission_denial_count == 0

    def test_real_run_with_an_allowed_read_outside_the_cwd_has_no_permission_denials(
        self,
    ):
        parsed = _read_transcript("read-outside-allowed-default")

        assert parsed.called_tool_names == ("Read",)
        assert parsed.permission_denial_count == 0

    def test_real_run_with_denied_grep_and_glob_counts_both_denials(self):
        parsed = _read_transcript("grep-glob-outside-denied")

        assert parsed.called_tool_names == ("Grep", "Glob")
        assert parsed.permission_denial_count == 2

    @pytest.mark.parametrize(
        "recording",
        sorted(path.stem for path in TRANSCRIPT_FIXTURES.glob("*.jsonl")),
    )
    def test_every_recorded_transcript_parses_to_a_result(self, recording):
        parsed = _read_transcript(recording)

        assert parsed.has_result is True
        assert parsed.session_config is not None

    def test_real_bad_model_run_is_an_error_with_no_model_id_and_a_note(self):
        parsed = _read_transcript("bad-model")

        assert parsed.has_result is True
        assert parsed.is_error is True
        assert parsed.cost_usd == 0
        assert parsed.model_id is None
        assert parsed.model_id_note

    def test_real_run_where_the_model_declines_bash_has_no_tool_use(self):
        parsed = _read_transcript("tool-denied-bash")

        assert parsed.called_tool_names == ()
        assert parsed.model_id == HAIKU_MODEL_ID

    def test_real_run_with_no_tools_has_no_tool_use(self):
        parsed = _read_transcript("no-tools")

        assert parsed.called_tool_names == ()
        assert parsed.result_text == "ok"
        assert parsed.has_result is True

    def test_blank_and_unparseable_lines_are_skipped(self):
        parsed = transcript.parse_stream(
            _stream("", "not json", "[1, 2]", _result_event("hi"), "   ")
        )

        assert (parsed.has_result, parsed.result_text) == (True, "hi")

    def test_rate_limit_and_system_events_are_ignored(self):
        parsed = transcript.parse_stream(
            _stream(
                {"type": "system", "subtype": "init", "tools": ["Read"]},
                {"type": "rate_limit_event", "rate_limit_info": {}},
                _tool_use_event("Read"),
                {"type": "rate_limit_event", "rate_limit_info": {}},
                _result_event("done"),
            )
        )

        assert parsed.called_tool_names == ("Read",)
        assert parsed.result_text == "done"

    def test_missing_result_event_reports_has_result_false(self):
        parsed = transcript.parse_stream(_stream(_tool_use_event("Grep")))

        assert parsed.has_result is False
        assert parsed.result_text is None
        assert parsed.called_tool_names == ("Grep",)
        assert parsed.cost_usd is None

    def test_zero_cost_is_reported_not_unknown(self):
        parsed = transcript.parse_stream(_stream(_result_event(total_cost_usd=0)))

        assert parsed.cost_usd == 0

    @pytest.mark.parametrize(
        "cost",
        [float("nan"), float("inf"), float("-inf"), -0.01, "0.01", True, None],
        ids=["nan", "inf", "-inf", "negative", "string", "bool", "null"],
    )
    def test_cost_that_is_not_a_finite_non_negative_number_is_unreported(self, cost):
        parsed = transcript.parse_stream(_stream(_result_event(total_cost_usd=cost)))

        assert parsed.has_result is True
        assert parsed.cost_usd is None

    def test_result_event_without_a_cost_field_is_unreported(self):
        event = _result_event()
        del event["total_cost_usd"]

        assert transcript.parse_stream(_stream(event)).cost_usd is None

    def test_empty_stdout_has_no_result(self):
        assert transcript.parse_stream("").has_result is False

    def test_missing_model_usage_gives_no_model_id_and_a_note(self):
        event = _result_event()
        del event["modelUsage"]

        parsed = transcript.parse_stream(_stream(event))

        assert parsed.model_id is None
        assert parsed.model_id_note

    def test_multiple_models_in_model_usage_are_ambiguous_and_noted(self):
        usage = {"claude-haiku-5-5": {}, "claude-sonnet-5-5": {}}

        parsed = transcript.parse_stream(_stream(_result_event(model_usage=usage)))

        assert parsed.model_id is None
        assert "claude-haiku-5-5" in parsed.model_id_note
        assert "claude-sonnet-5-5" in parsed.model_id_note

    def test_tool_names_from_several_assistant_events_keep_order_and_skip_text(self):
        text_block = {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "thinking"}]},
        }

        parsed = transcript.parse_stream(
            _stream(
                _tool_use_event("Read", "Grep"),
                text_block,
                _tool_use_event("WebFetch"),
                _result_event(),
            )
        )

        assert parsed.called_tool_names == ("Read", "Grep", "WebFetch")


class TestSessionConfig:
    def test_real_run_session_config_names_what_loaded_without_paths_or_ids(self):
        config = _read_transcript("pass-readonly").session_config

        assert config["model"] == HAIKU_MODEL_ID
        assert config["permissionMode"] == "default"
        assert config["tools"] == ["Glob", "Grep", "Read"]
        assert config["mcp_servers"] == []
        assert config["cwd"] == "<staged>"
        assert config["plugins"] and all(
            isinstance(name, str) and "/" not in name for name in config["plugins"]
        )
        assert set(config) == {
            "model",
            "permissionMode",
            "tools",
            "mcp_servers",
            "plugins",
            "cwd",
        }
        dumped = json.dumps(config)
        assert "/private" not in dumped and "/Users" not in dumped

    def test_init_event_is_scrubbed_of_cwd_session_id_and_plugin_paths(self):
        parsed = transcript.parse_stream(_stream(_init_event(), _result_event()))

        assert parsed.session_config == _expected_session_config(HAIKU_MODEL_ID)
        dumped = json.dumps(parsed.session_config)
        assert "/home/someone" not in dumped and "1111" not in dumped

    def test_mcp_servers_are_reported_by_name_only(self):
        init = _init_event(
            mcp_servers=[{"name": "codegraph", "status": "connected"}, "plain"]
        )

        parsed = transcript.parse_stream(_stream(init, _result_event()))

        assert parsed.session_config["mcp_servers"] == ["codegraph", "plain"]

    def test_stream_without_an_init_event_has_no_session_config(self):
        parsed = transcript.parse_stream(_stream(_result_event()))

        assert parsed.session_config is None

    def test_a_stream_cut_off_after_init_still_reports_the_session_config(self):
        parsed = transcript.parse_stream(_stream(_init_event()))

        assert parsed.has_result is False
        assert parsed.session_config == _expected_session_config(HAIKU_MODEL_ID)


# The unclosed-fence text below took about 3 s while either fence could match the
# newlines around it, and well under 0.1 s once neither does.
FENCE_SCAN_BUDGET_SECONDS = 1.5
BLANK_LINES_AFTER_FENCE = 20_000


class TestExtractAgentJson:
    def test_bare_object_is_parsed(self):
        assert transcript.extract_agent_json('{"status": "pass"}') == {"status": "pass"}

    def test_fenced_json_block_is_preferred_over_earlier_bare_object(self):
        text = 'Draft {"status": "fail"}\n```json\n{"status": "pass"}\n```'

        assert transcript.extract_agent_json(text) == {"status": "pass"}

    def test_two_objects_without_a_fence_first_wins(self):
        text = '{"status": "pass"} then {"status": "fail"}'

        assert transcript.extract_agent_json(text) == {"status": "pass"}

    def test_prose_around_the_object_is_ignored(self):
        text = 'Here is my review:\n{"status": "warn", "issues": []}\nHope it helps.'

        assert transcript.extract_agent_json(text) == {"status": "warn", "issues": []}

    def test_braces_inside_strings_do_not_break_balancing(self):
        text = 'x {"summary": "uses } and { inside", "status": "pass"} y'

        assert transcript.extract_agent_json(text) == {
            "summary": "uses } and { inside",
            "status": "pass",
        }

    def test_nested_objects_are_returned_whole(self):
        text = '{"issues": [{"severity": "error"}], "status": "fail"}'

        assert transcript.extract_agent_json(text)["issues"] == [{"severity": "error"}]

    @pytest.mark.parametrize(
        "opening", ["```json\n", "```json"], ids=["newline", "bare"]
    )
    def test_unclosed_fence_followed_by_many_blank_lines_is_scanned_in_bounded_time(
        self, opening
    ):
        text = opening + "\n" * BLANK_LINES_AFTER_FENCE

        started = time.monotonic()
        result = transcript.extract_agent_json(text)

        assert result is None
        assert time.monotonic() - started < FENCE_SCAN_BUDGET_SECONDS

    def test_fence_opened_with_trailing_spaces_and_a_carriage_return_is_parsed(self):
        text = '```json \t\r\n{"status": "pass"}\n```'

        assert transcript.extract_agent_json(text) == {"status": "pass"}

    def test_fenced_block_closed_after_blank_lines_and_an_indented_fence_is_parsed(
        self,
    ):
        text = '```json\n{"status": "pass"}\n\n\n  ```'

        assert transcript.extract_agent_json(text) == {"status": "pass"}

    def test_invalid_fenced_block_falls_back_to_a_bare_object(self):
        text = '```json\n{broken\n```\n{"status": "pass"}'

        assert transcript.extract_agent_json(text) == {"status": "pass"}

    @pytest.mark.parametrize(
        "text", ["", "no json here", "{not: json}", "[1, 2]", None]
    )
    def test_text_without_a_json_object_gives_none(self, text):
        assert transcript.extract_agent_json(text) is None

    def test_truncated_outer_object_does_not_yield_its_inner_object(self):
        assert transcript.extract_agent_json(TRUNCATED_OUTER_OBJECT) is None

    def test_object_inside_an_unclosed_outer_with_escaped_quote_is_not_top_level(self):
        text = r'{"summary": "say \"hi\" {", "issues": [{"severity": "error"}]'

        assert transcript.extract_agent_json(text) is None

    def test_top_level_object_after_a_closed_invalid_one_is_returned(self):
        text = '{not: json} then {"status": "pass"}'

        assert transcript.extract_agent_json(text) == {"status": "pass"}

    def test_apostrophe_or_quote_in_prose_before_the_object_is_ignored(self):
        text = 'It said "hello and then: {"status": "pass"}'

        assert transcript.extract_agent_json(text) == {"status": "pass"}
