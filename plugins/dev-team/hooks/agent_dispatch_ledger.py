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
that agent name as `matched_rule`. Anything not in the closed set — a typo, a
non-review team agent, or a fabricated name — is silently NOT recorded, never
written as free text: matching `boundary_events.py`'s own no-free-text
constraint (rule IDs / closed-vocabulary values only, never arbitrary
strings). `"record"` is a new, fifth-plus decision value: an observation, not
a block/warn/bypass/intervention/revert policy verdict — see
`knowledge/telemetry-schema.md` for its full documentation.

Fail-open, matching this codebase's own hook convention (and
`emit_boundary_event`'s own fail-open write side): any error here — a
missing/unreadable `agents/` directory, a malformed payload, an exception
from the shared helper — must never block a real Agent dispatch. This hook
always exits 0.

Contract (docs/python-hook-contract.md):
    Input : PreToolUse JSON on stdin (Agent/Task matcher)
    Output: always exit 0 — fail-open, this hook never blocks a dispatch.

Stdlib only. Python 3.8+. See ADR 0014 / ADR 0015.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HOOK_DIR = Path(__file__).resolve().parent
_LIB_DIR = _HOOK_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from boundary_events import emit_boundary_event as _emit_boundary_event  # noqa: E402
from review_agent_registry import registered_review_agent_names  # noqa: E402
from stdin_json import read_stdin_json  # noqa: E402


def emit_boundary_event(*args, **kwargs) -> None:
    """Local safety net (#859): even a misbehaving helper must never affect
    this hook's exit code, stdout, or stderr."""
    try:
        _emit_boundary_event(*args, **kwargs)
    except Exception:  # noqa: BLE001, S110 - fail-open by design
        pass


def _agents_dir_default() -> Path:
    # hooks/agent_dispatch_ledger.py -> hooks -> plugin root -> agents
    return _HOOK_DIR.parent / "agents"


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

    try:
        registered = registered_review_agent_names(_agents_dir_default())
    except Exception:  # noqa: BLE001 - fail-open: a broken registry read never blocks
        return 0

    if subagent_type not in registered:
        # Not a real, registered review agent — never recorded, not even as
        # a rejected/flagged entry (module docstring).
        return 0

    cwd = payload.get("cwd") or "."
    session_id = payload.get("session_id")
    tool_name = payload.get("tool_name") or "Agent"
    emit_boundary_event(
        cwd, "agent_dispatch_ledger", tool_name, "record", subagent_type, session_id
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 - fail-open: a hook bug must never block a dispatch
        sys.exit(0)
