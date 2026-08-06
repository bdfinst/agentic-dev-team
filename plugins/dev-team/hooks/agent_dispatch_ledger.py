#!/usr/bin/env python3
"""agent_dispatch_ledger.py — PreToolUse dispatch-ledger hook (#1461).

Registered in `settings.json`'s existing `PreToolUse` `"Agent|Task"` matcher
(alongside `context_ceiling_guard.py`). Records a `boundary-events.jsonl`
`"record"` event whenever a genuine review-agent dispatch fires, so
`hooks/pre_commit_review.py`'s `.review-passed` gate can later corroborate
that a hash-matching write was backed by real, independent Agent-tool
dispatches — not just a self-computed hash (issue #1461's residual gap; see
`hooks/lib/review_gate_hash.py`'s own docstring for the full account).

On each Agent/Task dispatch, reads `tool_input.subagent_type`. If and only if
it is present in `hooks/lib/review_agent_registry`'s closed set of registered
`agents/*-review.md` stems, records one `"record"` boundary event carrying
that agent name as `matched_rule`, stamped with a `subject_hash` binding this
dispatch to whatever content is under review right now, so a review of one
changeset can't later corroborate an unrelated one (#1461 security review).
Anything not in the closed set — a typo, a non-review team agent, or a
fabricated name — is silently NOT recorded, never written as free text:
matching `boundary_events.py`'s own no-free-text constraint (rule IDs /
closed-vocabulary values only, never arbitrary strings). `"record"` is a new,
fifth-plus decision value: an observation, not a block/warn/bypass/
intervention/revert policy verdict — see `knowledge/telemetry-schema.md` for
its full documentation.

**`subject_hash` selection (#1904 Bug 2b, revised from the original
staged-diff-only stamp):** the staged patch (`review_gate_hash()`) is empty
by definition during a `--since <base>`-scoped `/code-review` run
(`skills/pr/SKILL.md`'s only path to `gh pr create` — its step 1 requires a
CLEAN working tree before that review runs, so nothing is ever staged during
it). Stamping the constant `EMPTY_DIGEST` in that case would be exactly the
Bug 1 hazard `review_gate_hash.py`'s own docstring warns against, AND it
would leave this hook's evidence unable to corroborate
`hooks/pre_pr_review.py`'s gate at all for that mode (that gate always
compares against `branch_diff_gate_hash()`, never the staged-diff hash).
So: when the staged diff is empty, fall back to
`branch_diff_gate_hash(default_base_ref(cwd), cwd)` — the SAME content
domain `hooks/pre_pr_review.py` checks and `skills/code-review/SKILL.md`
step 9 now writes for a `--since <base>`-scoped review — and refuse to stamp
(`None`) rather than fall back to the empty digest a second time. The
ordinary auto-scope path (something IS staged) is unchanged: it still stamps
`review_gate_hash()`, matching step 9's own disclosed "identical only in the
common single-commit-then-PR shape" limitation for that mode.

Fail-open, matching this codebase's own hook convention (and
`emit_boundary_event`'s own fail-open write side): any error here — a
missing/unreadable `agents/` directory, a malformed payload, an exception
from the shared helper — must never block a real Agent dispatch. This hook
always exits 0.

KNOWN RESIDUAL GAP (#1461 security re-review): this module is itself a
directly executable script that reads an attacker-/self-controlled stdin
payload. Anyone with Bash access to this repo can run
`echo '{"tool_name":"Task","tool_input":{"subagent_type":"security-review"},
"cwd":"."}' | python3 hooks/agent_dispatch_ledger.py` (repeated with a second
registered agent stem) and produce two byte-genuine "record" rows, correctly
subject-hash-bound, with NO actual Agent/Task dispatch ever occurring. Locking
down `boundary_events.py`'s CLI (this module's sibling forgery vector) does
not close this one — the forge just moves one file over. Registered agent
names are public filenames, so the registry re-validation in
`review_gate_corroboration.py` does not help either. This is not fixable at
this module's level: it requires the harness itself to supply something a
hand-run process cannot fabricate (a signed dispatch receipt, or a
session/turn-identity check against a live stream the harness — not this
script — controls). Until that exists, this control raises the bar against
an agent that takes an *accidental* self-certification shortcut under
ambiguity (this issue's original, observed failure mode); it is not effective
against a deliberate, adversarial bypass. See
`hooks/pre_commit_review.py`'s module docstring for the matching disclosure
on the read side.

Contract (docs/python-hook-contract.md):
    Input : PreToolUse JSON on stdin (Agent/Task matcher)
    Output: always exit 0 — fail-open, this hook never blocks a dispatch.

Stdlib only. See ADR 0014 / ADR 0015.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HOOK_DIR = Path(__file__).resolve().parent
_LIB_DIR = _HOOK_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from boundary_events import emit_boundary_event as _emit_boundary_event
from review_agent_registry import (
    default_agents_dir,
    read_registered_review_agent_names,
    strip_plugin_prefix,
)
from review_gate_hash import (
    EMPTY_DIGEST,
    branch_diff_gate_hash,
    default_base_ref,
    review_gate_hash,
)
from stdin_json import read_stdin_json


def emit_boundary_event(*args, **kwargs) -> None:
    """Local safety net (#859): even a misbehaving helper must never affect
    this hook's exit code, stdout, or stderr."""
    try:
        _emit_boundary_event(*args, **kwargs)
    except Exception:  # noqa: BLE001, S110 - fail-open by design
        pass


def main() -> int:
    payload = read_stdin_json()
    if payload is None:
        # Empty or malformed stdin -> silent-pass.
        return 0

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0

    subagent_type = tool_input.get("subagent_type")
    if not isinstance(subagent_type, str) or not subagent_type:
        return 0

    # Normalize the plugin-qualified dispatch form ("dev-team:doc-review") to
    # the bare name the registry's closed set uses, so the plugin's normal,
    # installed invocation form is recognized identically to a bare-named one.
    subagent_type = strip_plugin_prefix(subagent_type)

    # #1904 item 1: `read_registered_review_agent_names()` returns `None` on
    # a registry read failure, distinct from a genuine `frozenset()` — but
    # this is the WRITE/POSITIVE-evidence side (recording that a dispatch
    # happened), where collapsing `None` to "don't record" is the safe
    # direction: narrowing corroboration can only narrow, never widen, what
    # counts as a passing gate later.
    registered = read_registered_review_agent_names(default_agents_dir())
    if not registered or subagent_type not in registered:
        # Not a real, registered review agent, or the registry could not be
        # read at all — never recorded, not even as a rejected/flagged entry
        # (module docstring).
        return 0

    cwd = payload.get("cwd") or "."
    session_id = payload.get("session_id")
    tool_name = payload.get("tool_name") or "Agent"

    # Stamp the CURRENT content hash (#1461 security review, revised #1904
    # Bug 2b) — binds this dispatch to whatever is under review right now,
    # so the corroboration reader can require dispatch evidence for the SAME
    # content as the eventual `.pr-review-passed` write, not merely "some
    # review happened recently" against unrelated content. A hash-
    # computation failure (e.g. no git repo) fails open per this hook's own
    # convention: still record the dispatch, just without a subject_hash —
    # such an event can never satisfy a gate check, which requires an exact
    # hash match, so this can only ever under-record, never forge evidence.
    try:
        subject_hash = review_gate_hash(cwd)
        if subject_hash == EMPTY_DIGEST:
            # Nothing staged — the routine state during a `--since <base>`-
            # scoped review (skills/pr/SKILL.md requires a clean working
            # tree before that review runs). Stamping EMPTY_DIGEST here
            # would be the exact Bug 1 hazard (a constant shared by every
            # such dispatch, regardless of real content) AND would leave
            # this evidence unable to corroborate `hooks/pre_pr_review.py`'s
            # gate, which always compares against `branch_diff_gate_hash()`.
            # Fall back to that same content domain; refuse to stamp (None)
            # rather than fall back to the empty digest a second time.
            base_ref = default_base_ref(cwd)
            branch_hash = branch_diff_gate_hash(base_ref, cwd) if base_ref is not None else None
            subject_hash = (
                branch_hash if branch_hash and branch_hash != EMPTY_DIGEST else None
            )
    except Exception:  # noqa: BLE001 - fail-open: a hash failure never blocks a dispatch
        subject_hash = None

    emit_boundary_event(
        cwd,
        "agent_dispatch_ledger",
        tool_name,
        "record",
        subagent_type,
        session_id,
        subject_hash=subject_hash,
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 - fail-open: a hook bug must never block a dispatch
        sys.exit(0)
