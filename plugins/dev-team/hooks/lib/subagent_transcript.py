"""hooks/lib/subagent_transcript.py — subagent-transcript readers shared by the
SubagentStop recorders (moved from `hooks/review_verdict_recorder.py`, names
made public, for #2270 Step 3.0 so `hooks/acceptance_examination_recorder.py`
reuses them instead of copying them).

Stdlib-only (json/pathlib/sys). See ADR 0014, ADR 0015.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

# lib/ -> scripts/lib/session_log/ is a documented reverse-dependency
# exception (see hooks/lib/cost_meter.py's identical import for the full
# rationale): session_log/ ships INSIDE this same plugin package,
# always present wherever a hook runs, and session_log itself imports
# nothing from hooks/lib/ (no cycle). This is a second instance of the
# `cost_meter.py` exception: the same direction (hooks/lib -> scripts/lib),
# the same sys.path.insert + bare-package-import mechanism.
_SCRIPTS_LIB_DIR = _LIB_DIR.parents[1] / "scripts" / "lib"
if str(_SCRIPTS_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_LIB_DIR))

from review_agent_registry import strip_plugin_prefix  # type: ignore[import-not-found]
from session_log import records as _records  # type: ignore[import-not-found]


def read_transcript_records(path: Path) -> list[dict] | None:
    """Every JSON-object row from `path`, or `None` when the transcript
    itself can't be used at all — missing, unreadable, or containing zero
    valid JSON lines. The three "malformed/unreadable transcript" Gherkin
    scenarios all collapse onto this one fail-open signal; a caller treats
    `None` and an empty-but-readable transcript identically (fail open,
    write nothing).

    Delegates to `session_log.records.iter_file_records` (imported above as
    `_records`, Fix #9 / #2166 correctness review) rather than
    `read_text()`-ing the whole transcript into memory: this hook has no
    need to distinguish "the trailing line is malformed JSON" as its own
    outcome the way `subagent_completion_guard.py`'s private `_tail_lines`/
    `_last_row` reader does (see that module's own docstring for why IT
    keeps a private reader) — `read_transcript_records` only ever needs
    "did this transcript yield at least one usable JSON object", which the
    shared streaming iterator answers just as well, at a fraction of the
    peak memory on a multi-MB transcript."""
    records: list[dict] = []
    saw_json = False
    for row in _records.iter_file_records(path):
        saw_json = True
        if isinstance(row, dict):
            records.append(row)
    return records if saw_json else None


def attribution_subagent_type(records: list[dict]) -> str | None:
    """Primary signal (see the "Spike finding" in the module docstring of
    `hooks/review_verdict_recorder.py`): the first non-empty native attribution
    value found on any record in the subagent's own transcript."""
    for rec in records:
        agent = _records.attribution_agent_of(rec)
        if agent:
            return agent
    return None


def own_agent_id(records: list[dict]) -> str | None:
    for rec in records:
        agent_id = rec.get("agentId")
        if isinstance(agent_id, str) and agent_id:
            return agent_id
    return None


def parent_transcript_path(subagent_transcript: Path) -> Path | None:
    """`<dir>/<session-id>/subagents/agent-<agentId>.jsonl` implies
    `<dir>/<session-id>.jsonl` (this step's own documented derivation).
    `None` when `subagent_transcript` doesn't match that layout."""
    subagents_dir = subagent_transcript.parent
    if subagents_dir.name != "subagents":
        return None
    session_dir = subagents_dir.parent
    return session_dir.parent / f"{session_dir.name}.jsonl"


def fallback_subagent_type(
    subagent_transcript: Path, records: list[dict]
) -> str | None:
    """The documented Task/Agent dispatch join, used only when the primary
    `attributionAgent` signal is absent from every record (see the "Spike
    finding" in the module docstring of `hooks/review_verdict_recorder.py`: the
    spike found no real transcript that needed this path)."""
    agent_id = own_agent_id(records)
    if not agent_id:
        return None
    parent_path = parent_transcript_path(subagent_transcript)
    if parent_path is None:
        return None
    parent_records = read_transcript_records(parent_path)
    if not parent_records:
        return None
    dispatch_types: dict[str, str] = {}
    agent_types: dict[str, str] = {}
    for rec in parent_records:
        _records.join_dispatch_agent_ids(rec, dispatch_types, agent_types)
    return agent_types.get(agent_id)


def resolve_subagent_type(subagent_transcript: Path, records: list[dict]) -> str | None:
    raw = attribution_subagent_type(records) or fallback_subagent_type(
        subagent_transcript, records
    )
    return strip_plugin_prefix(raw) if raw else None


def own_records_and_type(payload: dict) -> tuple[list[dict], str] | None:
    """The shared SubagentStop preamble: the stopping subagent's own transcript
    rows and its plugin-prefix-stripped `subagent_type`, or `None` when any
    step cannot resolve (no `transcript_path`, an unreadable or empty
    transcript, an unresolvable type). Callers treat `None` as "not
    ours" and return without writing."""
    transcript_path = payload.get("transcript_path")
    if not isinstance(transcript_path, str) or not transcript_path:
        return None
    transcript = resolve_subagent_transcript(
        Path(transcript_path), payload.get("agent_id")
    )
    records = read_transcript_records(transcript)
    if not records:
        return None
    subagent_type = resolve_subagent_type(transcript, records)
    return (records, subagent_type) if subagent_type else None


def message_text(message: object) -> str | None:
    """Assistant/user message `content` as plain text, whether it's a bare
    string or a Messages-API content-block list (only `text` blocks
    contribute; a block list with no text block returns `None`)."""
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "\n".join(parts) if parts else None
    return None


def first_turn_text(records: list[dict]) -> str | None:
    if not records:
        return None
    return message_text(records[0].get("message"))


def _tool_use_inputs(records: list[dict], name: str) -> Iterator[dict]:
    """The `input` dict of every `tool_use` block named `name`, in transcript
    order. Rows without a dict `message` or a list `content`, non-dict blocks,
    and blocks whose `input` is not a dict are skipped."""
    for rec in records:
        message = rec.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if (
                isinstance(block, dict)
                and block.get("type") == "tool_use"
                and block.get("name") == name
                and isinstance(block.get("input"), dict)
            ):
                yield block["input"]


def handback_message_text(records: list[dict]) -> str | None:
    """PRIMARY result-extraction path (Fix #1, #2166 correctness review —
    CRITICAL: this hook wrote zero rows in production before this fix).

    Verified directly against a real transcript in this session's own
    corpus before writing this (not assumed):
    `~/.claude/projects/-home-user-agentic-dev-team/<session-id>/subagents/
    agent-a006af1f32a025449.jsonl`, line 17 — a completed subagent's real
    final JSON result lives inside its OWN `SubagentHandback` tool_use
    block's `input.message` field (prose plus a fenced ```json block), never
    as the transcript's literal last row. The literal last row is a short
    wrap-up assistant turn ("Report delivered...") that comes AFTER the
    handback's own `tool_result` ack — exactly the shape
    `subagent_completion_guard.py`'s module docstring documents and confirms
    across 70 real transcripts ("Finding 3 — SubagentHandback is a real,
    distinguishable tool_use block"). Scans backward so the LAST handback
    call wins if a transcript ever carries more than one."""
    for handback_input in reversed(list(_tool_use_inputs(records, "SubagentHandback"))):
        text = handback_input.get("message")
        if isinstance(text, str) and text:
            return text
    return None


def fallback_last_parseable_turn_text(records: list[dict]) -> str | None:
    """FALLBACK ONLY (Fix #1): used when no `SubagentHandback` call is found
    anywhere in the transcript. This session's own corpus never needed this
    path (see `handback_message_text` above) — kept per the plan's explicit
    instruction for a transcript shape that never showed up in the sample.
    The last turn (scanning backward) whose text itself recovers as a JSON
    object via `extract_json_object`, rather than blindly trusting the
    transcript's literal last row the way the pre-fix code did."""
    for rec in reversed(records):
        text = message_text(rec.get("message"))
        if text and extract_json_object(text) is not None:
            return text
    return None


def last_assistant_text(records: list[dict]) -> str | None:
    """The text of the last assistant turn, or `None` when no assistant
    turn carries text. For an agent whose tool grant has no
    `SubagentHandback` (the acceptance examiner: `Bash` only) this is its
    final result. Unlike `fallback_last_parseable_turn_text` it does not
    scan back past a non-JSON final turn, so a stale JSON turn earlier in
    the transcript never stands in for the result."""
    for rec in reversed(records):
        message = rec.get("message")
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        text = message_text(message)
        if text and text.strip():
            return text
    return None


def final_result_text(records: list[dict]) -> str | None:
    """The text handed to `extract_json_object` for the agent's final JSON
    result: `handback_message_text` first, `fallback_last_parseable_turn_text`
    only when no handback call is present at all (Fix #1)."""
    return handback_message_text(records) or fallback_last_parseable_turn_text(records)


def extract_json_object(text: str) -> dict | None:
    """A small, tolerant JSON-object extractor for an agent's final-turn
    text: a clean parse first, then the first `{` to the last `}` span
    (recovers a fenced ```json block or a prose preamble/trailing
    sentence). Returns `None` for anything that isn't recoverable as a JSON
    object — the caller treats that as a malformed final result and fails
    open (zero rows), never guesses a verdict from a result it couldn't
    parse."""
    stripped = text.strip()
    if not stripped:
        return None
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        return parsed
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def resolve_subagent_transcript(transcript_path: Path, agent_id: object) -> Path:
    """The subagent's own transcript. The real SubagentStop payload's
    `transcript_path` is the PARENT session transcript; the subagent's lives
    at `<parent dir>/<parent stem>/subagents/agent-<agent_id>.jsonl`. Falls
    back to `transcript_path` itself when no `agent_id` is given or that file
    is absent (payloads that already point at the subagent transcript)."""
    if (
        isinstance(agent_id, str)
        and agent_id
        and "/" not in agent_id
        and "\\" not in agent_id
    ):
        candidate = (
            transcript_path.parent
            / transcript_path.stem
            / "subagents"
            / f"agent-{agent_id}.jsonl"
        )
        if candidate.is_file():
            return candidate
    return transcript_path


def bash_commands(records: list[dict]) -> list[str]:
    """The `input.command` string of every `Bash` `tool_use` block in
    `records`, in transcript order. A Bash block whose `input` isn't a dict,
    or whose `command` is missing or not a non-empty string, is skipped."""
    commands = (
        tool_input.get("command") for tool_input in _tool_use_inputs(records, "Bash")
    )
    return [command for command in commands if isinstance(command, str) and command]
