#!/usr/bin/env python3
"""hooks/review_verdict_recorder.py — SubagentStop per-lens verdict recorder
(#2166, Step 2.3; plan: plans/2164-verdict-ledger-writer.md, Decisions 3/4/4a).

## Contract (docs/python-hook-contract.md)

    Input : SubagentStop JSON on stdin (`transcript_path`, `session_id`, `cwd`)
    Output: zero or more `.claude/metrics/review-verdicts.jsonl` rows via
        `hooks/lib/review_verdicts.emit_review_verdict()` — one per in-scope
        file the dispatch prompt's Step 2.1 scope marker declared, each
        carrying `outcome: "pass"` or `"findings"`. Once `subagent_type` is
        confirmed a registered review lens, a degenerate exit (missing/
        reformatted scope marker, unparseable/malformed final result) also
        writes one `.claude/metrics/boundary-events.jsonl` `"record"`-decision
        row via `hooks/lib/boundary_events.emit_boundary_event()`, naming the
        reason (`missing-scope-marker` | `unparseable-result`) (Fix #3, #2166
        correctness review).
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
# exception (see hooks/lib/cost_meter.py's identical import for the full
# rationale): session_log/ ships INSIDE this same plugin package,
# always present wherever this hook runs, and session_log itself imports
# nothing from hooks/lib/ (no cycle). Mirrors cost_meter.py's own
# sys.path.insert + bare-package-import MECHANISM, not its directionality.
_SCRIPTS_LIB_DIR = _HOOK_DIR.parent / "scripts" / "lib"
if str(_SCRIPTS_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_LIB_DIR))

from boundary_events import emit_boundary_event  # type: ignore[import-not-found]
from review_agent_registry import (  # type: ignore[import-not-found]
    is_registered_review_lens,
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
    write nothing).

    Delegates to `session_log.records.iter_file_records` (imported above as
    `_records`, Fix #9 / #2166 correctness review) rather than
    `read_text()`-ing the whole transcript into memory: this hook has no
    need to distinguish "the trailing line is malformed JSON" as its own
    outcome the way `subagent_completion_guard.py`'s private `_tail_lines`/
    `_last_row` reader does (see that module's own docstring for why IT
    keeps a private reader) — `_read_transcript_records` only ever needs
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


def _handback_message_text(records: list[dict]) -> str | None:
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
    for rec in reversed(records):
        message = rec.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if (
                isinstance(block, dict)
                and block.get("type") == "tool_use"
                and block.get("name") == "SubagentHandback"
            ):
                handback_input = block.get("input")
                if isinstance(handback_input, dict):
                    text = handback_input.get("message")
                    if isinstance(text, str) and text:
                        return text
    return None


def _fallback_last_parseable_turn_text(records: list[dict]) -> str | None:
    """FALLBACK ONLY (Fix #1): used when no `SubagentHandback` call is found
    anywhere in the transcript. This session's own corpus never needed this
    path (see `_handback_message_text` above) — kept per the plan's explicit
    instruction for a transcript shape that never showed up in the sample.
    The last turn (scanning backward) whose text itself recovers as a JSON
    object via `_extract_json_object`, rather than blindly trusting the
    transcript's literal last row the way the pre-fix code did."""
    for rec in reversed(records):
        text = _message_text(rec.get("message"))
        if text and _extract_json_object(text) is not None:
            return text
    return None


def _final_result_text(records: list[dict]) -> str | None:
    """The text handed to `_extract_json_object` for the agent's final JSON
    result: `_handback_message_text` first, `_fallback_last_parseable_turn_text`
    only when no handback call is present at all (Fix #1)."""
    return _handback_message_text(records) or _fallback_last_parseable_turn_text(records)


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


def _resolve_under_cwd(file_path: str, cwd) -> Path | None:
    """Resolve `file_path` (a scope-marker entry or an `issues[].file`
    entry) against `cwd` to an absolute, symlink-resolved `Path`.

    This is the single normalized form both:
      * the path-traversal containment check (Fix #5, security review:
        a scope marker declaring `../../../../etc/passwd`-style paths must
        not be read/hashed outside `cwd`), and
      * the scope-marker/`issues[].file` membership comparison (Fix #2,
        correctness review: real review-agent transcripts in this session's
        own corpus report the SAME file in different path forms —
        relative vs. absolute — across different agents, so raw string
        equality silently missed genuine matches)
    key off of, so the two concerns share one resolution instead of two
    that could drift. Local replica of `finding_signature.py`'s own
    `_normalize_path` intent rather than an import of it:
    `hooks/lib/doc_classification.py`'s module docstring documents the
    established direction as `skills/*/scripts/` importing FROM `hooks/lib/`
    (`change_shape.py` reaches into `doc_classification.py`, never the
    reverse) — a hook importing `skills/code-review/scripts/finding_signature.py`
    would invert that.

    `None` on any resolution failure — rare, since `Path.resolve()` without
    `strict=` doesn't require the path to exist, but a broken symlink chain
    can still raise `OSError`."""
    try:
        target = Path(file_path)
        if not target.is_absolute():
            target = Path(cwd) / target
        return target.resolve()
    except OSError:
        return None


def _findings_files(issues: list, cwd) -> set[Path]:
    files: set[Path] = set()
    for issue in issues:
        if isinstance(issue, dict):
            file_path = issue.get("file")
            if isinstance(file_path, str) and file_path:
                resolved = _resolve_under_cwd(file_path, cwd)
                if resolved is not None:
                    files.add(resolved)
    return files


# 50 MiB cap (Fix #4, security review): bounds `_hash_file`'s read against a
# FIFO/device path or a multi-GB file hanging past this hook's fail-open
# exception wrapper in `main()` — a hang is not an exception `main()` can
# catch.
_MAX_HASH_FILE_BYTES = 50 * 1024 * 1024
_HASH_CHUNK_BYTES = 1 << 20  # 1 MiB incremental read


def _hash_file(path: Path) -> str | None:
    """Current-content sha256 hex digest of `path`, or `None` on any read
    failure (deleted, unreadable, not a regular file — a directory, FIFO, or
    device — or over `_MAX_HASH_FILE_BYTES`) — the caller skips just that
    one in-scope file rather than aborting the whole batch."""
    try:
        if not path.is_file():
            return None
        if path.stat().st_size > _MAX_HASH_FILE_BYTES:
            return None
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            while chunk := fh.read(_HASH_CHUNK_BYTES):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def process(payload: dict) -> None:
    """Fail-open SubagentStop processing (see module docstring Contract).

    Writes zero or more rows via `emit_review_verdict`; never raises —
    every input this function can't resolve confidently degrades to "write
    nothing" rather than a guess (Decision 4a: this hook trusts the dispatch
    prompt's declared scope, it does not independently re-verify it).

    Fix #3 (correctness review): the early returns below the point where
    `subagent_type` is confirmed to be a REGISTERED REVIEW LENS are
    observationally degenerate (zero rows, zero stderr, exit 0) the same way
    a legitimate no-op is — but unlike a legitimate no-op, they mean a
    dispatch that SHOULD have produced rows didn't. Those two exits
    (missing/reformatted scope marker, unparseable/malformed final result)
    each record one `boundary_events` `"record"`-decision row naming the
    reason, mirroring `subagent_completion_guard.py`'s own posture of
    surfacing a non-clean, explainable classification instead of staying
    silently indistinguishable from the happy path. The earlier,
    PRE-resolution early returns (missing transcript, unreadable transcript,
    unresolvable `subagent_type`, an entirely unregistered or a
    registered-but-non-review `subagent_type`) stay silent — those are
    legitimate no-ops: this dispatch was never confirmed to be a review
    lens that should have produced rows at all."""
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

    if not is_registered_review_lens(subagent_type):
        return

    # Past this point `subagent_type` is a confirmed, registered review
    # lens -- this dispatch SHOULD produce rows (Fix #3).
    cwd = resolve_cwd(payload)
    session_id = payload.get("session_id")

    first_text = _first_turn_text(records)
    in_scope = _parse_scope_marker(first_text) if first_text else None
    if not in_scope:
        emit_boundary_event(
            cwd,
            "review_verdict_recorder",
            "SubagentStop",
            "record",
            "missing-scope-marker",
            session_id=session_id,
        )
        return

    final_text = _final_result_text(records)
    result = _extract_json_object(final_text) if final_text else None
    issues = _issues_list(result)
    if issues is None:
        emit_boundary_event(
            cwd,
            "review_verdict_recorder",
            "SubagentStop",
            "record",
            "unparseable-result",
            session_id=session_id,
        )
        return
    findings_files = _findings_files(issues, cwd)

    cwd_resolved = Path(cwd).resolve()
    for file_path in in_scope:
        resolved = _resolve_under_cwd(file_path, cwd)
        if resolved is None or not resolved.is_relative_to(cwd_resolved):
            continue  # unresolvable, or outside cwd containment (Fix #5)
        file_hash = _hash_file(resolved)
        if file_hash is None:
            continue  # deleted/unreadable/non-regular/oversized -- skip this one only
        outcome = "findings" if resolved in findings_files else "pass"
        # Canonical, cwd-relative POSIX form (Fix #2, backstop review,
        # #2166 + #2171) -- not the raw scope-marker `file_path`, which can
        # name the same file in different forms (relative vs. absolute)
        # across different dispatch prompts. Decision 3 makes
        # `(lens, file_path, file_content_hash)` the future #2167 reader's
        # lookup key, so the same file's rows must consistently group under
        # one canonical path. Falls back to the absolute resolved form only
        # if `relative_to` fails -- not expected here, since the
        # containment check above already excludes anything outside
        # `cwd_resolved`.
        try:
            canonical_path = resolved.relative_to(cwd_resolved).as_posix()
        except ValueError:
            canonical_path = resolved.as_posix()
        emit_review_verdict(
            cwd, subagent_type, canonical_path, file_hash, outcome, session_id=session_id
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
