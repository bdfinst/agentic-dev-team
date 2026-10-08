"""Resolve one trial's outcome from the CLI run, its transcript and the grader.

Precedence when several conditions hold:
timeout > cli_error > tool_violation > parse_failure > graded_fail > pass.
Grading runs only when every earlier check passed.
"""

from __future__ import annotations

from collections.abc import Callable, Collection
from dataclasses import dataclass

from .runner import RunRecord
from .transcript import ParsedTranscript, extract_agent_json

OUTCOME_PASS = "pass"
OUTCOME_GRADED_FAIL = "graded_fail"
OUTCOME_PARSE_FAILURE = "parse_failure"
OUTCOME_TOOL_VIOLATION = "tool_violation"
OUTCOME_CLI_ERROR = "cli_error"
OUTCOME_TIMEOUT = "timeout"

MAX_TEXT_CHARS = 500

Grader = Callable[[dict], tuple[bool, list[str]]]


@dataclass(frozen=True)
class TrialResult:
    outcome: str
    cost_usd: float
    model_id: str | None
    model_id_note: str | None
    grader_messages: tuple[str, ...]
    error: str | None


def resolve_outcome(
    record: RunRecord,
    parsed: ParsedTranscript,
    enabled_tools: Collection[str],
    grader: Grader,
) -> TrialResult:
    """Apply the outcome precedence; `grader` is called only if all else passed."""
    outcome, error, messages = _decide(record, parsed, enabled_tools, grader)
    return TrialResult(
        outcome=outcome,
        cost_usd=parsed.cost_usd,
        model_id=parsed.model_id,
        model_id_note=parsed.model_id_note,
        grader_messages=tuple(_cap(m) for m in messages),
        error=_cap(error) if error is not None else None,
    )


def _decide(
    record: RunRecord,
    parsed: ParsedTranscript,
    enabled_tools: Collection[str],
    grader: Grader,
) -> tuple[str, str | None, list[str]]:
    if record.timed_out:
        return OUTCOME_TIMEOUT, "trial exceeded the time limit", []
    cli_error = _cli_error(record, parsed)
    if cli_error is not None:
        return OUTCOME_CLI_ERROR, cli_error, []
    violations = sorted(set(parsed.tool_names) - set(enabled_tools))
    if violations:
        return (
            OUTCOME_TOOL_VIOLATION,
            f"tools outside the enabled set: {', '.join(violations)}",
            [],
        )
    agent_json = extract_agent_json(parsed.result_text)
    if agent_json is None:
        return OUTCOME_PARSE_FAILURE, "no JSON object in the result text", []
    passed, messages = grader(agent_json)
    if not passed:
        return OUTCOME_GRADED_FAIL, None, messages
    return OUTCOME_PASS, None, []


def _cli_error(record: RunRecord, parsed: ParsedTranscript) -> str | None:
    if record.exit_code != 0:
        summary = f"exit code {record.exit_code}"
        detail = record.stderr.strip() or parsed.result_text
        return f"{summary}: {detail}" if detail else summary
    if parsed.is_error:
        return parsed.result_text or "result event reported is_error"
    if not parsed.has_result:
        return "no result event in stream"
    return None


def _cap(text: str) -> str:
    return text[:MAX_TEXT_CHARS]
