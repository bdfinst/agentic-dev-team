#!/usr/bin/env python3
"""verify_guard_edit_marker.py — PreToolUse hook (#708), sibling of
verify_guard.py.

Matcher: `Write|Edit|NotebookEdit`. Stamps verify_guard.py's per-session
state file to record that a real code edit happened since the last
verify-class Bash command. verify_guard.py reads this flag to tell a
genuinely stuck loop (same verify command, zero intervening edits) apart
from ordinary TDD re-verification (RED, GREEN, REFACTOR each legitimately
re-run the same command, but each preceded by an edit) before escalating
to a hard block.

This hook itself never warns or blocks — it only records a fact for its
sibling to read.

Contract (docs/python-hook-contract.md):
    Input : PreToolUse JSON on stdin (session_id, cwd)
    Output: none
    Exit  : always 0 (silent-pass)
    Env   : TMPDIR

Stdlib-only. Python 3.8+. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HOOK_DIR = Path(__file__).resolve().parent
_LIB_DIR = _HOOK_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from verify_guard_state import (
    read_state,
    state_file,
    state_key,
    write_state,
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
    session_id = str(payload.get("session_id") or "")
    cwd = str(payload.get("cwd") or "")
    key = state_key(session_id, cwd)
    path = state_file(key)

    data = read_state(path)
    data["edited"] = True
    # Preserve existing hash/count if present; a session with no verify
    # run yet simply gets an "edited" marker no verify_guard.py call will
    # ever compare against (a differing/absent hash already resets its
    # counter), so no need to seed hash/count here.
    write_state(path, data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
