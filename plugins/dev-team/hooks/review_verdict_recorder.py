#!/usr/bin/env python3
"""hooks/review_verdict_recorder.py — SubagentStop per-lens verdict recorder
(#2166, Step 2.3; plan: plans/2164-verdict-ledger-writer.md, Decisions 3/4/4a).

## Contract (docs/python-hook-contract.md)

    Input : SubagentStop JSON on stdin (`transcript_path`, `session_id`, `cwd`)
    Output: zero or more `.claude/metrics/review-verdicts.jsonl` rows via
        `hooks/lib/review_verdicts.emit_review_verdict()` — one per in-scope
        file the dispatch prompt's Step 2.1 scope marker declared, each
        carrying `outcome: "pass"` or `"findings"`.
    Posture: fail-open throughout. Any error, or any signal this hook can't
        resolve confidently (missing/unreadable/non-JSON transcript, an
        unresolvable `subagent_type`, an unregistered or registered-but-
        non-review `subagent_type`, a missing/reformatted scope marker, an
        unparseable/malformed final JSON result) -> zero rows written, exit
        0. A per-file read failure (a deleted/unreadable in-scope file)
        skips only that file — the rest still get their rows.

## Spike finding: `attributionAgent` reliability, checked against real
## transcripts before writing the rest of this hook (per this step's own
## instruction — not recalled/assumed)

`hooks/lib/cost_meter.py`'s "Attribution dimensions" docstring claims the
native top-level `attributionAgent` field is "present on every usage-bearing
sidechain record in real transcripts". Checked here directly against every
real subagent transcript from this session
(`~/.claude/projects/-home-user-agentic-dev-team/<session-id>/subagents/agent-*.jsonl`,
124 files, 10,795 total rows, 4,279 usage-bearing assistant rows):

  * 124/124 files carried an `attributionAgent` value on 100% (4,279/4,279)
    of their usage-bearing (assistant) records — no exceptions.
  * Exactly one distinct value per file, always — never absent-then-present
    partway through, never two different values in one file. The field
    identifies the whole dispatch, not just one turn.
  * Values are plugin-qualified for this plugin's own agents (e.g.
    `dev-team:structure-review`, `dev-team:correctness-review`,
    `dev-team:software-engineer`) and bare for harness-builtin agent types
    (`general-purpose`, `claude-code-guide`) — `strip_plugin_prefix`
    (`hooks/lib/review_agent_registry.py`) already normalizes exactly this,
    reused below rather than reimplemented.
  * The field is NOT stamped on every record in a subagent transcript — only
    the usage-bearing (assistant) ones. The transcript's first record (the
    dispatch-prompt `user` turn this hook also needs, for the Decision 3
    scope marker) never carries it, confirming as a side effect that "the
    dispatch prompt is the subagent's initial user message" holds in
    practice, not just in the plan's own claim.

**Conclusion: the primary signal is fully reliable in this corpus — no scope
change to this step.** The documented Task/Agent-dispatch-join fallback
(main-thread `tool_use.input.subagent_type` + `toolUseResult.agentId`,
matched against the subagent transcript's own `agentId`, with the parent
transcript path derived from `transcript_path`'s own directory structure) is
still implemented below, per the plan's explicit instruction — but the spike
found no real transcript that ever needed it.

Stdlib-only (hashlib/json/pathlib/sys). See ADR 0014, ADR 0015.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

_HOOK_DIR = Path(__file__).resolve().parent
_LIB_DIR = _HOOK_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

# hooks/ -> scripts/lib/session_log/ is a documented reverse-dependency
# exception (see hooks/lib/cost_meter.py's own module docstring for the
# full rationale): session_log/ ships INSIDE this same plugin package,
# always present wherever this hook runs, and session_log itself imports
# nothing from hooks/lib/ (no cycle). Mirrors cost_meter.py's own
# sys.path.insert + bare-package-import MECHANISM, not its directionality.
_SCRIPTS_LIB_DIR = _HOOK_DIR.parent / "scripts" / "lib"
if str(_SCRIPTS_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_LIB_DIR))

from review_agent_registry import (  # type: ignore[import-not-found]
    default_agents_dir,
    read_registered_review_agent_names,
    strip_plugin_prefix,
)
from review_verdicts import (  # type: ignore[import-not-found]
    SCOPE_MARKER_PREFIX,
    emit_review_verdict,
)
from session_log import records as _records  # type: ignore[import-not-found]
from stdin_json import read_stdin_json, resolve_cwd  # type: ignore[import-not-found]


def _read_transcript_records(path: Path) -> list[dict] | None:
    """Every JSON-object row from `path`, or `None` when the transcript
    itself can't be used at all — missing, unreadable, or containing zero
    valid JSON lines. The three "malformed/unreadable transcript" Gherkin
    scenarios all collapse onto this one fail-open signal; a caller treats
    `None` and an empty-but-readable transcript identically (fail open,
    write nothing)."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    records: list[dict] = []
    saw_json = False
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        saw_json = True
        if isinstance(row, dict):
            records.append(row)
    return records if saw_json else None


def _attribution_subagent_type(records: list[dict]) -> str | None:
    """Primary signal (see module docstring spike finding): the first
    non-empty native attribution value found on any record in the subagent's
    own transcript."""
    for rec in records:
        agent = _records.attribution_agent_of(rec)
        if agent:
            return agent
    return None


def _own_agent_id(records: list[dict]) -> str | None:
    for rec in records:
        agent_id = rec.get("agentId")
        if isinstance(agent_id, str) and agent_id:
            return agent_id
    return None


def _parent_transcript_path(subagent_transcript: Path) -> Path | None:
    """`<dir>/<session-id>/subagents/agent-<agentId>.jsonl` implies
    `<dir>/<session-id>.jsonl` (this step's own documented derivation).
    `None` when `subagent_transcript` doesn't match that layout."""
    subagents_dir = subagent_transcript.parent
    if subagents_dir.name != "subagents":
        return None
    session_dir = subagents_dir.parent
    return session_dir.parent / f"{session_dir.name}.jsonl"


def _fallback_subagent_type(subagent_transcript: Path, records: list[dict]) -> str | None:
    """The documented Task/Agent dispatch join, used only when the primary
    `attributionAgent` signal is absent from every record (see module
    docstring: the spike found no real transcript that needed this path)."""
    agent_id = _own_agent_id(records)
    if not agent_id:
        return None
    parent_path = _parent_transcript_path(subagent_transcript)
    if parent_path is None:
        return None
    parent_records = _read_transcript_records(parent_path)
    if not parent_records:
        return None
    dispatch_types: dict[str, str] = {}
    agent_types: dict[str, str] = {}
    for rec in parent_records:
        _records.join_dispatch_agent_ids(rec, dispatch_types, agent_types)
    return agent_types.get(agent_id)


def _resolve_subagent_type(subagent_transcript: Path, records: list[dict]) -> str | None:
    raw = _attribution_subagent_type(records) or _fallback_subagent_type(
        subagent_transcript, records
    )
    return strip_plugin_prefix(raw) if raw else None


def _message_text(message: object) -> str | None:
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


def _first_turn_text(records: list[dict]) -> str | None:
    if not records:
        return None
    return _message_text(records[0].get("message"))


def _last_turn_text(records: list[dict]) -> str | None:
    if not records:
        return None
    return _message_text(records[-1].get("message"))


def _parse_scope_marker(text: str) -> list[str] | None:
    """The in-scope file list from the Step 2.1 `SCOPE_MARKER_PREFIX` line,
    or `None` when no line starts with it — a missing/reformatted marker,
    which the caller treats as fail-open (zero rows)."""
    for line in text.splitlines():
        if line.startswith(SCOPE_MARKER_PREFIX):
            remainder = line[len(SCOPE_MARKER_PREFIX) :]
            return [f.strip() for f in remainder.split(",") if f.strip()]
    return None


def _extract_json_object(text: str) -> dict | None:
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


def _issues_list(result: dict | None) -> list | None:
    """`None` means "can't trust any verdict from this result" (missing or
    schema-drifted `issues`) — the caller fails open. A genuine empty list
    is a usable clean result (every in-scope file gets `pass`)."""
    if result is None:
        return None
    issues = result.get("issues")
    return issues if isinstance(issues, list) else None


def _findings_files(issues: list) -> set[str]:
    files: set[str] = set()
    for issue in issues:
        if isinstance(issue, dict):
            file_path = issue.get("file")
            if isinstance(file_path, str) and file_path:
                files.add(file_path)
    return files


def _hash_file(path: Path) -> str | None:
    """Current-content sha256 hex digest of `path`, or `None` on any read
    failure (deleted, unreadable, or a directory) — the caller skips just
    that one in-scope file rather than aborting the whole batch."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return hashlib.sha256(data).hexdigest()


def process(payload: dict) -> None:
    """Fail-open SubagentStop processing (see module docstring Contract).

    Writes zero or more rows via `emit_review_verdict`; never raises —
    every input this function can't resolve confidently degrades to "write
    nothing" rather than a guess (Decision 4a: this hook trusts the dispatch
    prompt's declared scope, it does not independently re-verify it)."""
    transcript_path = payload.get("transcript_path")
    if not isinstance(transcript_path, str) or not transcript_path:
        return
    transcript = Path(transcript_path)
    records = _read_transcript_records(transcript)
    if not records:
        return

    subagent_type = _resolve_subagent_type(transcript, records)
    if not subagent_type:
        return

    registered = read_registered_review_agent_names(default_agents_dir())
    if not registered or subagent_type not in registered:
        return

    first_text = _first_turn_text(records)
    in_scope = _parse_scope_marker(first_text) if first_text else None
    if not in_scope:
        return

    last_text = _last_turn_text(records)
    result = _extract_json_object(last_text) if last_text else None
    issues = _issues_list(result)
    if issues is None:
        return
    findings_files = _findings_files(issues)

    cwd = resolve_cwd(payload)
    session_id = payload.get("session_id")

    for file_path in in_scope:
        target = Path(file_path)
        if not target.is_absolute():
            target = Path(cwd) / target
        file_hash = _hash_file(target)
        if file_hash is None:
            continue  # deleted/unreadable in-scope file -- skip this one only
        outcome = "findings" if file_path in findings_files else "pass"
        emit_review_verdict(
            cwd, subagent_type, file_path, file_hash, outcome, session_id=session_id
        )


def main() -> int:
    """Fail-open SubagentStop entry point — see module docstring Contract."""
    try:
        payload = read_stdin_json() or {}
        process(payload)
    except Exception:  # noqa: BLE001, S110 — fail-open by design, see module docstring
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
