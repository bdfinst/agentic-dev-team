"""Examination verdict derivation for the acceptance examiner (#2270).

Pure, stdlib only, no I/O. Validates the examiner's handback against the plan's
criteria ids and the Bash commands it actually ran, and derives the record the
gate reads.

The record is written only by the SubagentStop hook, never relayed by
`/build`. `tainted` means a forbidden read or state-changing command was
detected by pattern; it is not proof of a violation and a clean record is not
proof of a clean run.

Self-attestation limit (#1461): the examiner reports its own rows. This module
checks completeness and that each claimed command appears in the transcript,
not that the observation is true. `agent_id` is stored in the record so a later
gate can corroborate it against the dispatch ledger.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone

MET = "met"
NOT_MET = "not-met"
INDETERMINATE = "indeterminate"
VERDICTS = (MET, NOT_MET, INDETERMINATE)
TAINTED = "tainted"

PROBLEM_INVALID_SHAPE = "invalid-result-shape"
PROBLEM_NO_CRITERIA = "no-acceptance-criteria"
PROBLEM_MISSING = "missing"
PROBLEM_DUPLICATE = "duplicate"
PROBLEM_UNKNOWN = "unknown"
PROBLEM_INCOMPLETE_ROW = "incomplete-row"
PROBLEM_INVALID_VERDICT = "invalid-verdict"
PROBLEM_COMMAND_NOT_RUN = "command-not-run"

_COMMAND_VERDICTS = (MET, NOT_MET)
RECORD_SCHEMA = 1

_FINDING_KEYS = ("kind", "target", "command")
_FD_DUPLICATION = re.compile(r"(?<!\S)\d*>&\d+(?!\S)")
_SEGMENT_SEPARATORS = re.compile(r"&&|\|\||;|\|")
_LEADING_CD = re.compile(r"^cd\s+\S+$")


def normalize_command(s: str) -> str:
    """Collapse runs of whitespace to single spaces and strip the ends."""
    return " ".join(s.split())


def _segments(command: str) -> list[str]:
    """Normalized, non-empty segments of one Bash call, minus a leading `cd`."""
    without_dups = _FD_DUPLICATION.sub(" ", command)
    parts = [normalize_command(p) for p in _SEGMENT_SEPARATORS.split(without_dups)]
    if parts and _LEADING_CD.match(parts[0]):
        parts = parts[1:]
    return [p for p in parts if p]


def ran_segments(commands: list[str]) -> set[str]:
    """Every complete segment of every Bash call in `commands`."""
    return {segment for command in commands for segment in _segments(command)}


def derive_overall(rows: list[dict], audit_findings: list, problems: list[str]) -> str:
    """The record's overall verdict.

    Precedence: `tainted` (any audit finding), `indeterminate` (any problem),
    `not-met` (any not-met row), `indeterminate` (any indeterminate row), `met`.
    Callers pass the `problems` from `validate_rows`, which flags a plan with
    no criteria, so empty `rows` with no problems is not a real input.
    """
    if audit_findings:
        return TAINTED
    if problems:
        return INDETERMINATE
    verdicts = {row.get("verdict") for row in rows}
    if NOT_MET in verdicts:
        return NOT_MET
    if INDETERMINATE in verdicts:
        return INDETERMINATE
    return MET


def _is_blank(value: object) -> bool:
    return not isinstance(value, str) or not value.strip()


def _well_formed_rows(result: object) -> list[dict] | None:
    """The result's rows, or `None` when the handback has the wrong shape."""
    if not isinstance(result, dict):
        return None
    rows = result.get("criteria")
    if not isinstance(rows, list):
        return None
    for row in rows:
        if not isinstance(row, dict):
            return None
        if not isinstance(row.get("criterion"), str):
            return None
        if not isinstance(row.get("verdict"), str):
            return None
    return rows


def _coverage_problems(counts: Counter, expected_ids: list[str]) -> list[str]:
    problems = [PROBLEM_NO_CRITERIA] if not expected_ids else []
    missing = [cid for cid in expected_ids if cid not in counts]
    if missing:
        problems.append(f"{PROBLEM_MISSING} {','.join(missing)}")
    problems += [f"{PROBLEM_DUPLICATE} {cid}" for cid, n in counts.items() if n > 1]
    problems += [
        f"{PROBLEM_UNKNOWN} {cid}" for cid in counts if cid not in expected_ids
    ]
    return problems


def _command_was_run(claimed: str, ran: set[str]) -> bool:
    segments = _segments(claimed)
    return len(segments) == 1 and segments[0] in ran


def _row_problems(row: dict, ran: set[str]) -> list[str]:
    cid, verdict = row["criterion"], row["verdict"]
    problems = []
    if verdict not in VERDICTS:
        problems.append(f"{PROBLEM_INVALID_VERDICT} {cid} {verdict}")
    needs_command = verdict in _COMMAND_VERDICTS
    if _is_blank(row.get("observation")) or (
        needs_command and _is_blank(row.get("command"))
    ):
        problems.append(f"{PROBLEM_INCOMPLETE_ROW} {cid}")
    elif needs_command and not _command_was_run(row["command"], ran):
        problems.append(f"{PROBLEM_COMMAND_NOT_RUN} {cid}")
    return problems


def _row_results(
    rows: list[dict], counts: Counter, expected_ids: list[str], ran: set[str]
) -> tuple[list[dict], list[str]]:
    usable, problems = [], []
    for row in rows:
        row_problems = _row_problems(row, ran)
        problems += row_problems
        cid = row["criterion"]
        if not row_problems and counts[cid] == 1 and cid in expected_ids:
            usable.append(row)
    return usable, problems


def validate_rows(
    result: object, expected_ids: list[str], ran_commands: list[str]
) -> tuple[list[dict], list[str]]:
    """Check the examiner's handback; return (usable rows, problems).

    A usable row names an expected id exactly once and has no row-level
    problem. Any input shape is accepted; a wrong-shaped `result` yields
    `invalid-result-shape` and no rows, never an exception.
    """
    rows = _well_formed_rows(result)
    if rows is None:
        no_criteria = [] if expected_ids else [PROBLEM_NO_CRITERIA]
        return [], [PROBLEM_INVALID_SHAPE, *no_criteria]
    counts = Counter(row["criterion"] for row in rows)
    ran = ran_segments(ran_commands)
    usable, row_problems = _row_results(rows, counts, expected_ids, ran)
    return usable, _coverage_problems(counts, expected_ids) + row_problems


def build_record(
    plan_id: str,
    rows: list[dict],
    audit_findings: list[dict],
    problems: list[str],
    binding_hash: str,
    inputs_digest: str,
    agent_id: str,
) -> dict:
    """The examination record the SubagentStop hook persists."""
    return {
        "schema": RECORD_SCHEMA,
        "plan": plan_id,
        "agent_id": agent_id,
        "overall": derive_overall(rows, audit_findings, problems),
        "criteria": list(rows),
        "audit_findings": [
            {key: finding.get(key) for key in _FINDING_KEYS}
            for finding in audit_findings
        ],
        "problems": list(problems),
        "binding_hash": binding_hash,
        "inputs_digest": inputs_digest,
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
