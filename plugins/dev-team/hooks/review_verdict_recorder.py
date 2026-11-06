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
    (`hooks/lib/review_agent_registry.py`) already normalizes exactly this;
    `hooks/lib/subagent_transcript.py` applies it.
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
still implemented, per the plan's explicit instruction, in
`hooks/lib/subagent_transcript.py` — but the spike found no real transcript
that ever needed it.

Stdlib-only (contextlib/pathlib/sys). See ADR 0014, ADR 0015.
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

_HOOK_DIR = Path(__file__).resolve().parent
_LIB_DIR = _HOOK_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import subagent_transcript  # type: ignore[import-not-found]
from boundary_events import emit_boundary_event  # type: ignore[import-not-found]
from review_agent_registry import (
    is_registered_review_lens,  # type: ignore[import-not-found]
)
from review_verdicts import (  # type: ignore[import-not-found]
    canonical_path,
    emit_review_verdict,
    parse_scope_marker,
)
from review_verdicts import (
    hash_file as _hash_file,
)

_PLUGIN_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(_PLUGIN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_SCRIPTS_DIR))

from instrument_log import append_row  # type: ignore[import-not-found]
from stdin_json import read_stdin_json, resolve_cwd  # type: ignore[import-not-found]


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
    entry) against `cwd` to an absolute, symlink-resolved `Path` contained
    within `cwd` — `None` when it can't be resolved or escapes `cwd` (a
    `../../../../etc/passwd`-style traversal, Fix #5 security review).

    Thin wrapper over the shared `review_verdicts.canonical_path` (#2167):
    that function IS this one's containment-and-normalization logic, kept
    in `hooks/lib/` so `scripts/verdict_scope.py`'s reader canonicalizes the
    SAME way this writer does — real review-agent transcripts in this
    session's own corpus report the SAME file in different path forms
    (relative vs. absolute) across different agents (Fix #2, correctness
    review), so a caller with its own second copy of this logic would drift
    from the writer's own canonical form and silently never match a genuine
    row."""
    canonical = canonical_path(file_path, cwd)
    if canonical is None:
        return None
    return Path(cwd).resolve() / canonical


def _findings_files(issues: list, cwd) -> set[Path]:
    files: set[Path] = set()
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        file_path = issue.get("file")
        if not isinstance(file_path, str) or not file_path:
            continue
        resolved = _resolve_under_cwd(file_path, cwd)
        if resolved is not None:
            files.add(resolved)
    return files


def _log_abort_scan(lens: str, issues: list, cwd, session_id) -> None:
    """One `checkpoint-aborts` row per parsed lens result, so the stream is
    written whether or not the model ran `checkpoint_abort.py`. Records only
    whether this result alone would trip the abort rule; the deferred-lens
    list needs the round's full lens order, which only the checkpoint knows.
    Fail-open."""
    with contextlib.suppress(Exception):  # fail-open by design
        # Imported here, inside the suppress, so a break in the abort
        # module's import chain cannot stop verdict recording.
        from checkpoint_abort import decide_abort  # type: ignore[import-not-found]

        # Schema-drifted issues (non-dict, or missing severity/confidence)
        # can never qualify, and `decide_abort` rejects them outright.
        well_formed_issues = [
            i
            for i in issues
            if isinstance(i, dict) and "severity" in i and "confidence" in i
        ]
        decision = decide_abort([{"agent": lens, "issues": well_formed_issues}], [lens])
        append_row(
            "checkpoint-aborts",
            {
                "source": "stop-hook",
                "mode": "abort",
                "aborted": decision["aborted"],
                "triggering_agent": decision["triggeringAgent"],
                "deferred_lenses": [],
            },
            cwd=cwd,
            session_id=session_id,
        )


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
    resolved = subagent_transcript.own_records_and_type(payload)
    if resolved is None:
        return
    records, subagent_type = resolved

    if not is_registered_review_lens(subagent_type):
        return

    # Past this point `subagent_type` is a confirmed, registered review
    # lens -- this dispatch SHOULD produce rows (Fix #3).
    cwd = resolve_cwd(payload)
    session_id = payload.get("session_id")

    first_text = subagent_transcript.first_turn_text(records)
    in_scope = parse_scope_marker(first_text) if first_text else None
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

    final_text = subagent_transcript.final_result_text(records)
    result = subagent_transcript.extract_json_object(final_text) if final_text else None
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
    _log_abort_scan(subagent_type, issues, cwd, session_id)
    findings_files = _findings_files(issues, cwd)
    # #2167 correctness review: per-file membership in `findings_files`
    # alone recorded `pass` for every in-scope file whenever this lens's
    # issues carried no `file` field, a `file` outside/unmapped to scope, or
    # simply didn't happen to name one of THIS dispatch's files — even for a
    # `status: "fail"`/`"warn"` result. Once #2167 acts on a `pass` row to
    # skip a future dispatch, that silently erased the round's own verdict.
    # A lens result that isn't clean marks every in-scope file `"findings"`,
    # never just the ones an issue happens to name.
    status = result.get("status") if isinstance(result, dict) else None
    lens_result_is_clean = status in ("pass", "skip")

    cwd_resolved = Path(cwd).resolve()
    for file_path in in_scope:
        canonical = canonical_path(file_path, cwd)
        if canonical is None:
            continue  # unresolvable, or outside cwd containment (Fix #5)
        resolved = cwd_resolved / canonical
        file_hash = _hash_file(resolved)
        if file_hash is None:
            continue  # deleted/unreadable/non-regular/oversized -- skip this one only
        outcome = (
            "pass"
            if lens_result_is_clean and resolved not in findings_files
            else "findings"
        )
        emit_review_verdict(
            cwd, subagent_type, canonical, file_hash, outcome, session_id=session_id
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
