"""Transcript builders for the acceptance-examination recorder tests (#2270).

Each builder returns the JSONL rows a real `acceptance-examiner` subagent
transcript carries, in the shapes `hooks/lib/subagent_transcript.py` resolves:
a dispatch prompt as the first `user` turn, `Bash` `tool_use` blocks with
their `tool_result` acks, and a `SubagentHandback` tail (mirrors
`_handback_tail` in `test_review_verdict_recorder.py`). `attributionAgent`
rides on the assistant rows, as it does in real transcripts.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path

from examination_inputs import PLAN_MARKER_PREFIX  # type: ignore[import-not-found]

EXAMINER = "acceptance-examiner"
AGENT_ID = "agent-examiner-1"
SESSION_ID = "sess-1"
_PARENT_TRANSCRIPT = "session.jsonl"
_BASH_CALL_COUNTER = itertools.count(1)


def dispatch_row(marker_plan_rel: str | None, agent_id: str = AGENT_ID) -> dict:
    """The dispatch-prompt turn; `None` leaves the plan marker out."""
    marker = f"\n\n{PLAN_MARKER_PREFIX}{marker_plan_rel}\n" if marker_plan_rel else ""
    return {
        "type": "user",
        "agentId": agent_id,
        "message": {
            "role": "user",
            "content": f"Examine the acceptance criteria.{marker}",
        },
    }


def _tool_result_row(tool_use_id: str, agent_id: str) -> dict:
    return {
        "type": "user",
        "agentId": agent_id,
        "message": {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": tool_use_id}],
        },
    }


def _tool_use_row(
    name: str, tool_input: dict, tool_use_id: str, agent_id: str, attribution: str
) -> dict:
    return {
        "type": "assistant",
        "isSidechain": True,
        "agentId": agent_id,
        "attributionAgent": attribution,
        "message": {
            "role": "assistant",
            "stop_reason": "tool_use",
            "content": [
                {
                    "type": "tool_use",
                    "id": tool_use_id,
                    "name": name,
                    "input": tool_input,
                }
            ],
        },
    }


def bash_call_rows(
    command: str, agent_id: str = AGENT_ID, attribution_agent: str = EXAMINER
) -> list[dict]:
    """One `Bash` call and its result ack."""
    tool_use_id = f"toolu_bash_{next(_BASH_CALL_COUNTER)}"
    return [
        _tool_use_row(
            "Bash", {"command": command}, tool_use_id, agent_id, attribution_agent
        ),
        _tool_result_row(tool_use_id, agent_id),
    ]


def handback_rows(
    message_text: str, agent_id: str = AGENT_ID, attribution_agent: str = EXAMINER
) -> list[dict]:
    """The handback call, its ack, and a wrap-up turn that is not the result."""
    tool_use_id = f"toolu_handback_{agent_id}"
    return [
        _tool_use_row(
            "SubagentHandback",
            {"message": message_text},
            tool_use_id,
            agent_id,
            attribution_agent,
        ),
        _tool_result_row(tool_use_id, agent_id),
        {
            "type": "assistant",
            "isSidechain": True,
            "agentId": agent_id,
            "attributionAgent": attribution_agent,
            "message": {
                "role": "assistant",
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "Report delivered."}],
            },
        },
    ]


def write_transcript(
    directory: Path, rows: list[dict], agent_id: str = AGENT_ID
) -> Path:
    """Write `rows` where the harness puts a subagent transcript and return the
    parent transcript path a `SubagentStop` payload carries (that file need not
    exist; the recorder locates the subagent file from `agent_id`)."""
    parent = directory / _PARENT_TRANSCRIPT
    subagent = directory / parent.stem / "subagents" / f"agent-{agent_id}.jsonl"
    subagent.parent.mkdir(parents=True, exist_ok=True)
    subagent.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    return parent


def stop_payload(
    cwd: Path | str, transcript: Path | str, agent_id: str = AGENT_ID
) -> dict:
    """The `SubagentStop` stdin payload."""
    return {
        "cwd": str(cwd),
        "transcript_path": str(transcript),
        "agent_id": agent_id,
        "session_id": SESSION_ID,
    }
