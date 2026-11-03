#!/usr/bin/env python3
"""hooks/acceptance_examination_recorder.py — SubagentStop recorder for the
acceptance examiner (#2270, Step 3.2; plan: plans/2270-acceptance-examiner.md,
Design decisions 1-5, 9, 10).

## Contract (docs/python-hook-contract.md)

    Input : SubagentStop JSON on stdin (`transcript_path`, `agent_id`,
        `session_id`, `cwd`). The examiner's OWN transcript is read: the
        payload's `transcript_path` is the parent session's, so the subagent
        file is located from the payload's `agent_id`
        (`subagent_transcript.resolve_subagent_transcript`).
    Output: for an `acceptance-examiner` stop, one atomic
        `.claude/memory/acceptance-examination-<plan>.json` record (replacing
        any earlier record for that plan) built from the examiner's handback,
        the Bash commands it ran, the read audit, and the current binding.
        Boundary events (`.claude/metrics/boundary-events.jsonl`, decision
        `record`, tool `SubagentStop`), none carrying path or command text:
        `missing-plan-marker` (no plan marker in the first user turn; no
        record is written) and `examiner-forbidden-read` (one event when the
        read audit found anything; the record is `tainted`).
    Posture: fail-open throughout. Any error exits 0 with empty stdout and
        stderr and writes no partial file (`write_record` is atomic). The hook
        never blocks. A missing record is what the acceptance-examination
        gate refuses on, so a failed hook still fails the gate closed.

The hook is the sole record writer (decision 1); `/build` never relays a
verdict. It returns without a record or an event for any non-examiner
subagent, an unreadable transcript, a plan that cannot be located inside the
repository, or a repository that cannot be resolved.

## SubagentStop ordering

Whether this hook completes before the Agent tool result returns to the
caller is not yet observed (decision 10). `/build` Step 7.6 therefore polls
for the record (`status --wait`).

SubagentStop ordering, first live observation: pending (recorded at the Pre-PR gate's seeded-defect check).

Stdlib-only. See ADR 0014, ADR 0015.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HOOK_DIR = Path(__file__).resolve().parent
_LIB_DIR = _HOOK_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import subagent_transcript  # type: ignore[import-not-found]
from boundary_events import emit_boundary_event  # type: ignore[import-not-found]
from examination_inputs import (  # type: ignore[import-not-found]
    criteria_ids,
    parse_plan_marker,
    plan_examination_inputs,
)
from examination_store import (  # type: ignore[import-not-found]
    Binding,
    NotARepository,
    binding_for_plan,
    canonical_plan_id,
    is_binding_hash,
    record_path,
    repo_root,
    write_record,
)
from examination_verdict import (  # type: ignore[import-not-found]
    PROBLEM_BASE_UNRESOLVABLE,
    PROBLEM_UNPARSEABLE,
    build_record,
    validate_rows,
)
from examiner_read_audit import audit_commands  # type: ignore[import-not-found]
from stdin_json import read_stdin_json, resolve_cwd  # type: ignore[import-not-found]

HOOK_NAME = "acceptance_examination_recorder"
EXAMINER_AGENT = "acceptance-examiner"
EVENT_TOOL = "SubagentStop"
EVENT_DECISION = "record"
RULE_MISSING_PLAN_MARKER = "missing-plan-marker"
RULE_FORBIDDEN_READ = "examiner-forbidden-read"


def _emit(cwd: str, rule: str, session_id: object) -> None:
    """One boundary event; the vocabulary carries no path or command text."""
    emit_boundary_event(
        cwd,
        HOOK_NAME,
        EVENT_TOOL,
        EVENT_DECISION,
        rule,
        session_id=session_id if isinstance(session_id, str) else None,
    )


def _examiner_records(payload: dict) -> list[dict] | None:
    """The examiner's own transcript rows, or `None` for any other subagent
    (or an unreadable transcript)."""
    transcript_path = payload.get("transcript_path")
    if not isinstance(transcript_path, str) or not transcript_path:
        return None
    transcript = subagent_transcript.resolve_subagent_transcript(
        Path(transcript_path), payload.get("agent_id")
    )
    records = subagent_transcript.read_transcript_records(transcript)
    if not records:
        return None
    subagent_type = subagent_transcript.resolve_subagent_type(transcript, records)
    return records if subagent_type == EXAMINER_AGENT else None


def _read_plan(plan_path: Path) -> str | None:
    try:
        return plan_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _agent_id(records: list[dict], payload: dict) -> str:
    agent_id = subagent_transcript.own_agent_id(records) or payload.get("agent_id")
    return str(agent_id) if agent_id else ""


def _rows_and_problems(
    records: list[dict], expected: list[str], ran: list[str]
) -> tuple[list[dict], list[str]]:
    """The usable criterion rows and the problems found in the handback."""
    text = subagent_transcript.handback_message_text(records)
    result = subagent_transcript.extract_json_object(text) if text else None
    if result is None:
        return [], [PROBLEM_UNPARSEABLE]
    return validate_rows(result, expected, ran)


def _examination(
    records: list[dict],
    agent_id: str,
    plan_id: str,
    plan_text: str,
    binding: Binding,
    audit_scope: tuple[str, str],
) -> tuple[dict, list[dict]]:
    """The record for this stop and the audit findings behind it (pure).
    `audit_scope` is the repository root and the examiner's cwd."""
    expected = criteria_ids(plan_examination_inputs(plan_text))
    ran = subagent_transcript.bash_commands(records)
    rows, problems = _rows_and_problems(records, expected, ran)
    findings = [f._asdict() for f in audit_commands(ran, *audit_scope)]
    if not is_binding_hash(binding.hash):
        problems = [*problems, PROBLEM_BASE_UNRESOLVABLE]
    return build_record(plan_id, rows, findings, problems, binding, agent_id), findings


def process(payload: dict, cwd: str) -> None:
    """Fail-open SubagentStop processing (see module docstring Contract).

    I/O happens only through the transcript read, the plan read, the record
    write, and the boundary events (plus the store's bounded git calls for the
    root and the binding). Every input it cannot resolve returns without a
    record."""
    records = _examiner_records(payload)
    if records is None:
        return
    session_id = payload.get("session_id")

    first_text = subagent_transcript.first_turn_text(records)
    plan_rel = parse_plan_marker(first_text) if first_text else None
    if plan_rel is None:
        _emit(cwd, RULE_MISSING_PLAN_MARKER, session_id)
        return

    try:
        root = repo_root(cwd)
        plan_id = canonical_plan_id(root / plan_rel, root)
    except (NotARepository, ValueError):
        return
    plan_text = _read_plan(root / plan_id)
    if plan_text is None:
        return

    record, findings = _examination(
        records,
        _agent_id(records, payload),
        plan_id,
        plan_text,
        binding_for_plan(root, plan_id, plan_text),
        (str(root), cwd),
    )
    write_record(record_path(root, plan_id), record)
    if findings:
        _emit(cwd, RULE_FORBIDDEN_READ, session_id)


def main() -> int:
    """Fail-open SubagentStop entry point — see module docstring Contract."""
    try:
        payload = read_stdin_json() or {}
        process(payload, resolve_cwd(payload))
    except Exception:  # noqa: BLE001, S110 — fail-open by design, see module docstring
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
