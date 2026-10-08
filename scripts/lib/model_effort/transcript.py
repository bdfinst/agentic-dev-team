"""Parse a `claude -p --output-format stream-json` transcript.

Reads the raw stdout line by line and keeps only what trial grading needs: the
final result text, error flag, cost, the resolved model ID, and the names of the
tools the agent called. Unparseable lines and event types that carry none of
that (`system`, `rate_limit_event`, ...) are skipped.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

EVENT_RESULT = "result"
EVENT_ASSISTANT = "assistant"
BLOCK_TOOL_USE = "tool_use"

FENCED_JSON_PATTERN = re.compile(r"```json\s*\n(.*?)\n\s*```", re.DOTALL)


@dataclass(frozen=True)
class ParsedTranscript:
    result_text: str | None
    is_error: bool
    cost_usd: float
    model_id: str | None
    model_id_note: str | None
    tool_names: tuple[str, ...]
    has_result: bool


def parse_stream(stdout: str) -> ParsedTranscript:
    """Fold the stream into a `ParsedTranscript`; the last `result` event wins."""
    tool_names: list[str] = []
    result_event: dict | None = None
    for event in _iter_events(stdout):
        event_type = event.get("type")
        if event_type == EVENT_RESULT:
            result_event = event
        elif event_type == EVENT_ASSISTANT:
            tool_names.extend(_tool_names(event))

    if result_event is None:
        return ParsedTranscript(
            result_text=None,
            is_error=False,
            cost_usd=0.0,
            model_id=None,
            model_id_note="no result event in stream",
            tool_names=tuple(tool_names),
            has_result=False,
        )
    model_id, note = _resolve_model_id(result_event.get("modelUsage"))
    return ParsedTranscript(
        result_text=_as_optional_str(result_event.get("result")),
        is_error=bool(result_event.get("is_error")),
        cost_usd=_as_cost(result_event.get("total_cost_usd")),
        model_id=model_id,
        model_id_note=note,
        tool_names=tuple(tool_names),
        has_result=True,
    )


def extract_agent_json(text: str | None) -> dict | None:
    """Return the agent's JSON object: a fenced ```json block, else the first parseable `{...}`."""
    if not text:
        return None
    for fenced in FENCED_JSON_PATTERN.findall(text):
        parsed = _decode_object(fenced.strip(), 0)
        if parsed is not None:
            return parsed
    return _first_bare_object(text)


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


def _as_cost(value) -> float:
    is_number = isinstance(value, (int, float)) and not isinstance(value, bool)
    return float(value) if is_number else 0.0


def _first_bare_object(text: str) -> dict | None:
    start = text.find("{")
    while start != -1:
        parsed = _decode_object(text, start)
        if parsed is not None:
            return parsed
        start = text.find("{", start + 1)
    return None


def _decode_object(text: str, start: int) -> dict | None:
    try:
        value, _ = json.JSONDecoder().raw_decode(text, start)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None
