"""Resolve one trial's outcome from the CLI run, its transcript and the grader.

Precedence when several conditions hold is the declaration order of `Outcome`.
Grading runs only when every earlier check passed. A grader reports the agent's
answer being wrong as a failed verdict; an error it raises is a harness fault and
propagates.
"""

from __future__ import annotations

from collections.abc import Callable, Collection
from dataclasses import dataclass
from enum import StrEnum

from .path_scrub import scrub_paths
from .runner import RunRecord
from .transcript import ParsedTranscript, extract_agent_json

MAX_MESSAGE_CHARS = 500

Grader = Callable[[dict], tuple[bool, list[str]]]


class Outcome(StrEnum):
    """Trial outcomes, highest precedence first. Values are the artifact's JSON strings."""

    TIMEOUT = "timeout"
    CLI_ERROR = "cli_error"
    TOOL_VIOLATION = "tool_violation"
    PARSE_FAILURE = "parse_failure"
    GRADED_FAIL = "graded_fail"
    PASS = "pass"


# Infrastructure failures, as opposed to the agent's answer being wrong.
INFRA_OUTCOMES = frozenset({Outcome.CLI_ERROR, Outcome.TIMEOUT})


@dataclass(frozen=True)
class TrialResult:
    outcome: Outcome
    cost_usd: float
    model_id: str | None
    model_id_note: str | None
    grader_messages: tuple[str, ...]
    error: str | None
    session_config: dict | None = None
    # False when the stream reported no usable cost; `cost_usd` is then 0.0, not a measurement.
    cost_reported: bool = True


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
        cost_usd=parsed.cost_usd or 0.0,
        model_id=parsed.model_id,
        model_id_note=parsed.model_id_note,
        grader_messages=_truncate_messages(messages),
        error=_truncate(scrub_paths(error, record.cwd)) if error is not None else None,
        session_config=parsed.session_config,
        cost_reported=parsed.cost_usd is not None,
    )


def _decide(
    record: RunRecord,
    parsed: ParsedTranscript,
    enabled_tools: Collection[str],
    grader: Grader,
) -> tuple[Outcome, str | None, list[str]]:
    if record.timed_out:
        return Outcome.TIMEOUT, "trial exceeded the time limit", []
    cli_error = _cli_error(record, parsed)
    if cli_error is not None:
        return Outcome.CLI_ERROR, cli_error, []
    violations = sorted(set(parsed.tool_names) - set(enabled_tools))
    if violations:
        return (
            Outcome.TOOL_VIOLATION,
            f"tools outside the enabled set: {', '.join(violations)}",
            [],
        )
    agent_json = extract_agent_json(parsed.result_text)
    if agent_json is None:
        return Outcome.PARSE_FAILURE, "no JSON object in the result text", []
    return _grade(agent_json, grader)


def _grade(agent_json: dict, grader: Grader) -> tuple[Outcome, str | None, list[str]]:
    passed, messages = grader(agent_json)
    if not passed:
        return Outcome.GRADED_FAIL, None, messages
    return Outcome.PASS, None, []


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


def _truncate(text: str, limit: int = MAX_MESSAGE_CHARS) -> str:
    return text[:limit]


def _truncate_messages(messages: list[str]) -> tuple[str, ...]:
    """Keep messages in order until their combined length reaches the cap."""
    kept: list[str] = []
    remaining = MAX_MESSAGE_CHARS
    for message in messages:
        if remaining <= 0:
            break
        kept.append(_truncate(message, remaining))
        remaining -= len(kept[-1])
    return tuple(kept)
