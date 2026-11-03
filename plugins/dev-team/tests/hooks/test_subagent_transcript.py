"""Tests for hooks/lib/subagent_transcript.py (#2270, Step 3.0).

The transcript helpers were lifted verbatim out of
`hooks/review_verdict_recorder.py`; `test_review_verdict_recorder.py` still
exercises them end-to-end through the hook. This file covers them directly,
plus the new `bash_commands`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parents[2] / "hooks" / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import subagent_transcript  # type: ignore[import-not-found]

_REVIEW_AGENT = "structure-review"


def _tool_use(name: str, tool_input: object) -> dict:
    return {"type": "tool_use", "id": "toolu_x", "name": name, "input": tool_input}


def _assistant_row(*blocks: dict) -> dict:
    return {
        "type": "assistant",
        "message": {"role": "assistant", "content": list(blocks)},
    }


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    return path


# ---------------------------------------------------------------------------
# bash_commands
# ---------------------------------------------------------------------------


def test_bash_commands_of_empty_records_is_empty() -> None:
    assert subagent_transcript.bash_commands([]) == []


def test_bash_commands_returns_the_command_of_one_bash_call() -> None:
    records = [_assistant_row(_tool_use("Bash", {"command": "git status"}))]
    assert subagent_transcript.bash_commands(records) == ["git status"]


def test_bash_commands_ignores_non_bash_tool_calls_and_text_blocks() -> None:
    records = [
        _assistant_row(
            {"type": "text", "text": "looking"},
            _tool_use("Read", {"file_path": "/a"}),
            _tool_use("Bash", {"command": "ls"}),
        ),
        {"type": "user", "message": {"role": "user", "content": "plain string"}},
        _assistant_row(_tool_use("Grep", {"command": "not-bash"})),
    ]
    assert subagent_transcript.bash_commands(records) == ["ls"]


def test_bash_commands_skips_non_string_missing_and_empty_commands() -> None:
    records = [
        _assistant_row(
            _tool_use("Bash", {"command": 42}),
            _tool_use("Bash", {}),
            _tool_use("Bash", {"command": ""}),
            _tool_use("Bash", "not-a-dict"),
            _tool_use("Bash", {"command": "echo ok"}),
        ),
        {"type": "assistant"},
        {"type": "assistant", "message": "not-a-dict"},
        {"type": "assistant", "message": {"content": "not-a-list"}},
    ]
    assert subagent_transcript.bash_commands(records) == ["echo ok"]


def test_bash_commands_preserves_order_across_rows_and_blocks() -> None:
    records = [
        _assistant_row(
            _tool_use("Bash", {"command": "first"}),
            _tool_use("Bash", {"command": "second"}),
        ),
        _assistant_row(_tool_use("Bash", {"command": "third"})),
    ]
    assert subagent_transcript.bash_commands(records) == ["first", "second", "third"]


# ---------------------------------------------------------------------------
# read_transcript_records
# ---------------------------------------------------------------------------


def test_read_transcript_records_returns_none_for_a_missing_file(
    tmp_path: Path,
) -> None:
    assert subagent_transcript.read_transcript_records(tmp_path / "nope.jsonl") is None


def test_read_transcript_records_returns_none_when_no_line_is_json(
    tmp_path: Path,
) -> None:
    path = tmp_path / "t.jsonl"
    path.write_text("not json\n", encoding="utf-8")
    assert subagent_transcript.read_transcript_records(path) is None


def test_read_transcript_records_keeps_only_json_objects(tmp_path: Path) -> None:
    path = tmp_path / "t.jsonl"
    path.write_text('{"a": 1}\n[1, 2]\n{"b": 2}\n', encoding="utf-8")
    assert subagent_transcript.read_transcript_records(path) == [{"a": 1}, {"b": 2}]


# ---------------------------------------------------------------------------
# resolve_subagent_transcript
# ---------------------------------------------------------------------------


def test_resolve_subagent_transcript_finds_the_agent_file_next_to_the_parent(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "session-1.jsonl"
    agent_file = tmp_path / "session-1" / "subagents" / "agent-abc.jsonl"
    _write_jsonl(agent_file, [{"agentId": "abc"}])
    assert subagent_transcript.resolve_subagent_transcript(parent, "abc") == agent_file


def test_resolve_subagent_transcript_falls_back_to_the_given_path(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "session-1.jsonl"
    assert subagent_transcript.resolve_subagent_transcript(parent, None) == parent
    assert subagent_transcript.resolve_subagent_transcript(parent, "../x") == parent


# ---------------------------------------------------------------------------
# message_text / first_turn_text
# ---------------------------------------------------------------------------


def test_message_text_joins_text_blocks_of_a_block_list() -> None:
    message = {
        "content": [
            {"type": "text", "text": "a"},
            {"type": "tool_use"},
            {"type": "text", "text": "b"},
        ]
    }
    assert subagent_transcript.message_text(message) == "a\nb"


def test_message_text_returns_a_bare_string_content_as_is() -> None:
    assert subagent_transcript.message_text({"content": "hello"}) == "hello"


def test_message_text_returns_none_without_a_text_block() -> None:
    assert subagent_transcript.message_text({"content": [{"type": "tool_use"}]}) is None
    assert subagent_transcript.message_text("not-a-dict") is None


def test_first_turn_text_reads_the_first_record_only() -> None:
    records = [
        {"message": {"content": "dispatch prompt"}},
        {"message": {"content": "later"}},
    ]
    assert subagent_transcript.first_turn_text(records) == "dispatch prompt"
    assert subagent_transcript.first_turn_text([]) is None


# ---------------------------------------------------------------------------
# final_result_text / handback_message_text / extract_json_object
# ---------------------------------------------------------------------------


def test_final_result_text_prefers_the_last_handback_call_over_the_last_row() -> None:
    records = [
        _assistant_row(_tool_use("SubagentHandback", {"message": "early"})),
        _assistant_row(
            _tool_use("SubagentHandback", {"message": '{"status": "pass"}'})
        ),
        {"message": {"role": "assistant", "content": "Report delivered."}},
    ]
    assert subagent_transcript.final_result_text(records) == '{"status": "pass"}'


def test_final_result_text_falls_back_to_the_last_turn_that_parses_as_json() -> None:
    records = [
        {"message": {"role": "assistant", "content": '{"status": "pass"}'}},
        {"message": {"role": "assistant", "content": "Report delivered."}},
    ]
    assert subagent_transcript.final_result_text(records) == '{"status": "pass"}'


def test_final_result_text_is_none_when_nothing_parses() -> None:
    records = [{"message": {"role": "assistant", "content": "no json here"}}]
    assert subagent_transcript.final_result_text(records) is None


def test_extract_json_object_recovers_a_fenced_block() -> None:
    text = 'Done.\n```json\n{"status": "pass", "issues": []}\n```\n'
    assert subagent_transcript.extract_json_object(text) == {
        "status": "pass",
        "issues": [],
    }


def test_extract_json_object_rejects_non_objects_and_garbage() -> None:
    assert subagent_transcript.extract_json_object("[1, 2]") is None
    assert subagent_transcript.extract_json_object("   ") is None
    assert subagent_transcript.extract_json_object("{broken") is None


# ---------------------------------------------------------------------------
# attribution_subagent_type / own_agent_id / parent_transcript_path
# ---------------------------------------------------------------------------


def test_attribution_subagent_type_is_the_first_non_empty_attribution() -> None:
    records = [
        {"type": "user"},
        {"type": "assistant", "attributionAgent": "dev-team:structure-review"},
    ]
    assert (
        subagent_transcript.attribution_subagent_type(records)
        == "dev-team:structure-review"
    )
    assert subagent_transcript.attribution_subagent_type([{"type": "user"}]) is None


def test_own_agent_id_is_the_first_non_empty_string_agent_id() -> None:
    records = [{"agentId": ""}, {"agentId": 7}, {"agentId": "abc"}]
    assert subagent_transcript.own_agent_id(records) == "abc"
    assert subagent_transcript.own_agent_id([{}]) is None


def test_parent_transcript_path_derives_the_session_file() -> None:
    sub = Path("/p/session-1/subagents/agent-abc.jsonl")
    assert subagent_transcript.parent_transcript_path(sub) == Path("/p/session-1.jsonl")
    assert (
        subagent_transcript.parent_transcript_path(Path("/p/agent-abc.jsonl")) is None
    )


# ---------------------------------------------------------------------------
# resolve_subagent_type (+ dispatch-join fallback)
# ---------------------------------------------------------------------------


def test_resolve_subagent_type_strips_the_plugin_prefix_from_attribution(
    tmp_path: Path,
) -> None:
    records = [{"type": "assistant", "attributionAgent": f"dev-team:{_REVIEW_AGENT}"}]
    assert (
        subagent_transcript.resolve_subagent_type(tmp_path / "t.jsonl", records)
        == _REVIEW_AGENT
    )


# ---------------------------------------------------------------------------
# Unit-level coverage of the documented Task/Agent dispatch-join fallback
# (used only when attributionAgent is absent from every record -- the spike
# recorded in review_verdict_recorder.py's own module docstring found no real transcript that
# needed it, but the fallback is still implemented per the plan and exercised
# here directly rather than left dead).
# ---------------------------------------------------------------------------


def test_fallback_resolves_subagent_type_via_task_agent_join(tmp_path: Path) -> None:
    session_dir = tmp_path / "session-1"
    subagents_dir = session_dir / "subagents"
    subagents_dir.mkdir(parents=True)

    agent_transcript_path = subagents_dir / "agent-abc123.jsonl"
    subagent_rows = [
        {
            "type": "user",
            "agentId": "abc123",
            "message": {"role": "user", "content": "Review a.py"},
        },
        {
            "type": "assistant",
            "isSidechain": True,
            "agentId": "abc123",
            # No attributionAgent field at all on any record.
            "message": {"role": "assistant", "content": "done"},
        },
    ]
    with agent_transcript_path.open("w", encoding="utf-8") as fh:
        for row in subagent_rows:
            fh.write(json.dumps(row) + "\n")

    parent_transcript = tmp_path / "session-1.jsonl"
    parent_rows = [
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "Task",
                        "input": {"subagent_type": f"dev-team:{_REVIEW_AGENT}"},
                    }
                ],
            },
        },
        {
            "type": "user",
            "toolUseResult": {"agentId": "abc123"},
            "message": {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "toolu_1"}],
            },
        },
    ]
    with parent_transcript.open("w", encoding="utf-8") as fh:
        for row in parent_rows:
            fh.write(json.dumps(row) + "\n")

    records = subagent_transcript.read_transcript_records(agent_transcript_path)
    resolved = subagent_transcript.resolve_subagent_type(agent_transcript_path, records)
    assert resolved == _REVIEW_AGENT
