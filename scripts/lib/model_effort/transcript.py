"""Parse a `claude -p --output-format stream-json` transcript.

Reads the raw stdout line by line and keeps only what trial grading needs: the
final result text, error flag, cost, the resolved model ID, the names of the
tools the agent called, the permission denial count, and a scrubbed copy of the
`system`/`init` event (the session configuration). Unparseable lines and event
types that carry none of that (`rate_limit_event`, ...) are skipped.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass

from .path_scrub import STAGED_PLACEHOLDER

EVENT_RESULT = "result"
EVENT_ASSISTANT = "assistant"
EVENT_SYSTEM = "system"
SUBTYPE_INIT = "init"
BLOCK_TOOL_USE = "tool_use"

# Neither fence may match newlines beside the line break it needs: the opening
# fence ends at the first line break and the closing fence is indented but opens
# its own line. Otherwise a long run of blank lines after an unclosed fence takes
# quadratic time to scan. The body is stripped by the caller.
FENCED_JSON_PATTERN = re.compile(r"```json[ \t\r]*\n(.*?)\n[ \t\r]*```", re.DOTALL)


@dataclass(frozen=True)
class ParsedTranscript:
    result_text: str | None
    is_error: bool
    # `None` when the stream did not report a usable cost: no result event, or a
    # cost that is missing, not a number, not finite or negative.
    cost_usd: float | None
    model_id: str | None
    model_id_note: str | None
    called_tool_names: tuple[str, ...]
    has_result: bool
    permission_denial_count: int = 0
    session_config: dict | None = None


def parse_stream(stdout: str) -> ParsedTranscript:
    """Fold the stream into a `ParsedTranscript`; the last `result` event wins."""
    tool_names: list[str] = []
    result_event: dict | None = None
    session_config: dict | None = None
    for event in _iter_events(stdout):
        event_type = event.get("type")
        if event_type == EVENT_RESULT:
            result_event = event
        elif event_type == EVENT_ASSISTANT:
            tool_names.extend(_tool_names(event))
        elif _is_init_event(event) and session_config is None:
            session_config = _scrub_init(event)

    if result_event is None:
        return ParsedTranscript(
            result_text=None,
            is_error=False,
            cost_usd=None,
            model_id=None,
            model_id_note="no result event in stream",
            called_tool_names=tuple(tool_names),
            has_result=False,
            session_config=session_config,
        )
    model_id, note = _resolve_model_id(result_event.get("modelUsage"))
    return ParsedTranscript(
        result_text=_as_optional_str(result_event.get("result")),
        is_error=bool(result_event.get("is_error")),
        cost_usd=_as_cost(result_event.get("total_cost_usd")),
        model_id=model_id,
        model_id_note=note,
        called_tool_names=tuple(tool_names),
        has_result=True,
        permission_denial_count=_count_denials(result_event.get("permission_denials")),
        session_config=session_config,
    )


def extract_agent_json(text: str | None) -> dict | None:
    """Return the agent's JSON object: a fenced ```json block, else the first parseable `{...}`."""
    if not text:
        return None
    for fenced in FENCED_JSON_PATTERN.findall(text):
        parsed = _decode_object(fenced.strip(), 0)
        if parsed is not None:
            return parsed
    # Fenced blocks were tried above; blank them so an unclosed `{` in one cannot
    # swallow a later top-level object.
    return _first_bare_object(FENCED_JSON_PATTERN.sub(" ", text))


def _iter_events(stdout: str):
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            yield event


def _is_init_event(event: dict) -> bool:
    return event.get("type") == EVENT_SYSTEM and event.get("subtype") == SUBTYPE_INIT


def _scrub_init(init_event: dict) -> dict:
    """Keep what the session loaded, without paths or identifiers.

    Dropped: session and event IDs, the API key source, slash commands, agents,
    plugin paths and sources, and the cwd, which is replaced by a placeholder.
    """
    return {
        "model": _as_optional_str(init_event.get("model")),
        "permissionMode": _as_optional_str(init_event.get("permissionMode")),
        "tools": _string_items(init_event.get("tools")),
        "mcp_servers": _names(init_event.get("mcp_servers")),
        "plugins": _names(init_event.get("plugins")),
        "cwd": STAGED_PLACEHOLDER,
    }


def _string_items(value) -> list[str]:
    return (
        [item for item in value if isinstance(item, str)]
        if isinstance(value, list)
        else []
    )


def _names(entries) -> list[str]:
    """Names from a list of strings or of objects with a `name` field."""
    if not isinstance(entries, list):
        return []
    names = [
        entry.get("name") if isinstance(entry, dict) else entry for entry in entries
    ]
    return [name for name in names if isinstance(name, str)]


def _count_denials(value) -> int:
    return len(value) if isinstance(value, list) else 0


def _tool_names(assistant_event: dict) -> list[str]:
    message = assistant_event.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return []
    return [
        block["name"]
        for block in content
        if isinstance(block, dict)
        and block.get("type") == BLOCK_TOOL_USE
        and isinstance(block.get("name"), str)
    ]


def _resolve_model_id(model_usage) -> tuple[str | None, str | None]:
    if not isinstance(model_usage, dict) or not model_usage:
        return None, "modelUsage missing or empty"
    if len(model_usage) > 1:
        return None, f"modelUsage has several models: {', '.join(sorted(model_usage))}"
    return next(iter(model_usage)), None


def _as_optional_str(value) -> str | None:
    return value if isinstance(value, str) else None


def _as_cost(value) -> float | None:
    is_number = isinstance(value, (int, float)) and not isinstance(value, bool)
    if not is_number or not math.isfinite(value) or value < 0:
        return None
    return float(value)


def _first_bare_object(text: str) -> dict | None:
    for start in _top_level_brace_starts(text):
        parsed = _decode_object(text, start)
        if parsed is not None:
            return parsed
    return None


def _top_level_brace_starts(text: str):
    """Yield each `{` that opens at brace depth 0, skipping braces inside JSON strings.

    Quotes only open a string once inside a brace, so prose quotes before the object
    are ignored. An unclosed object keeps its inner `{` off depth 0.
    """
    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"' and depth:
            in_string = True
        elif char == "{":
            if depth == 0:
                yield index
            depth += 1
        elif char == "}" and depth:
            depth -= 1


def _decode_object(text: str, start: int) -> dict | None:
    try:
        value, _ = json.JSONDecoder().raw_decode(text, start)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None
