#!/usr/bin/env python3
"""Python port of hooks/verify-guard.sh (#608 / #572 Phase 3), escalated to a
hard stop for stuck loops (#708).

PreToolUse Bash hook — detects repeated identical verify invocations
within a session. Once the same normalized command has run THRESHOLD
consecutive times with **zero** intervening Edit/Write/NotebookEdit calls
(tracked via verify_guard_edit_marker.py, its PreToolUse sibling on the
Write|Edit|NotebookEdit matcher), it BLOCKS the command instead of merely
warning — that combination is a genuinely stuck loop, not the ordinary
RED/GREEN/REFACTOR pattern of re-running the same command after each real
edit. Any edit observed since the previous verify run resets the counter,
same as a different command does, so legitimate TDD repeats are never
blocked.

Contract (docs/python-hook-contract.md):
    Input : PreToolUse JSON on stdin (hook_event_name, session_id,
            tool_input.command, cwd)
    Output: Warning on stdout below threshold; `[BLOCK]`-prefixed message
            at/above threshold (unless DEV_TEAM_VERIFY_THRESHOLD=0)
    Exit  : 0 below threshold, or when DEV_TEAM_VERIFY_THRESHOLD=0;
            2 (block) at/above threshold with threshold > 0
    Env   : DEV_TEAM_VERIFY_THRESHOLD (default 3), TMPDIR

Stdlib-only. Python 3.8+. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

_HOOK_DIR = Path(__file__).resolve().parent
_LIB_DIR = _HOOK_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from boundary_events import emit_boundary_event as _emit_boundary_event
from verify_guard_state import (
    cksum,
    read_state,
    state_file,
    state_key,
    write_state,
)


def emit_boundary_event(*args, **kwargs) -> None:
    """Local safety net (#859): even a misbehaving helper must never affect
    this hook's exit code, stdout, or stderr."""
    try:
        _emit_boundary_event(*args, **kwargs)
    except Exception:  # noqa: BLE001 - fail-open by design
        pass


# Verify-class command detector — mirrors `session_extract.py::_VERIFY_RE`.
_VERIFY_RE = re.compile(
    r"\b("
    r"npm (run )?(test|lint|build)"
    r"|pytest|bats|eslint|tsc|go test|cargo (test|build)|mvn"
    r"|gradle|make( |$)|vitest|jest|ruff|mypy|shellcheck"
    r")\b"
)


def _read_payload() -> dict:
    try:
        raw = sys.stdin.buffer.read()
    except (OSError, ValueError):
        return {}
    try:
        return json.loads(raw or b"{}")
    except json.JSONDecodeError:
        return {}


def main() -> int:
    payload = _read_payload()
    cmd = str(payload.get("tool_input", {}).get("command") or "")
    if not cmd:
        return 0

    # Only fire on verify-class commands.
    if not _VERIFY_RE.search(cmd):
        return 0

    session_id = str(payload.get("session_id") or "")
    cwd = str(payload.get("cwd") or "")
    key = state_key(session_id, cwd)
    path = state_file(key)

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return 0

    # Normalize the command (collapse whitespace) for comparison.
    norm_cmd = " ".join(cmd.split())
    norm_hash = cksum(norm_cmd)

    try:
        threshold = int(os.environ.get("DEV_TEAM_VERIFY_THRESHOLD", "3"))
    except ValueError:
        threshold = 3

    prev = read_state(path)
    prev_hash = str(prev.get("hash") or "")
    prev_count = int(prev.get("count") or 0)
    edited_since_prev = bool(prev.get("edited"))

    # Consecutive count increments only when the exact same normalized
    # command runs again with NO edit in between — an edit resets the
    # counter exactly like a different command does (existing behavior).
    if norm_hash == prev_hash and not edited_since_prev:
        count = prev_count + 1
    else:
        count = 1

    # Persist state. This run has "consumed" any pending edit signal, so
    # the flag is cleared here; verify_guard_edit_marker.py sets it again
    # the next time an Edit/Write/NotebookEdit call is observed.
    write_state(path, {"hash": norm_hash, "count": count, "edited": False})

    # Match the historical `[ "$count" -ge "$THRESHOLD" ]` semantics —
    # threshold=0 always fires on the first run too. The "set to 0 to
    # suppress" message is technically misleading for the advisory (byte
    # parity with the original .sh is the contract there), but threshold=0
    # DOES fully suppress the new block below: escalating a hook whose own
    # docs claim to be a full opt-out would violate that opt-out.
    if count < threshold:
        return 0

    if threshold <= 0:
        print(
            f"verify-guard: This verify command has run {count} consecutive "
            "times without a code change."
        )
        print(
            "  If the tests are still failing, change the code rather than "
            "re-running the same command."
        )
        print("  To suppress this warning, set DEV_TEAM_VERIFY_THRESHOLD=0.")
        emit_boundary_event(
            cwd, "verify_guard", "Bash", "warn", "verify-repeat-threshold", session_id
        )
        return 0

    print(
        f"[BLOCK] verify-guard: This verify command has run {count} "
        "consecutive times without a code change."
    )
    print()
    print(
        "  No Edit/Write/NotebookEdit happened between these runs — that's a "
        "stuck loop, not TDD's RED/GREEN/REFACTOR pattern (which always has "
        "a real edit between repeats of the same command)."
    )
    print(
        "  Run a systematic-debugging pass (see the systematic-debugging "
        "skill) to find the root cause, then make the code change the "
        "tests are waiting for before re-running this command."
    )
    print(
        "  If the root cause is understood but unresolvable in scope, stop "
        "and escalate per /build's Escalation step instead of retrying "
        "again."
    )
    print("  To suppress this block, set DEV_TEAM_VERIFY_THRESHOLD=0.")
    emit_boundary_event(
        cwd, "verify_guard", "Bash", "block", "verify-repeat-threshold", session_id
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
