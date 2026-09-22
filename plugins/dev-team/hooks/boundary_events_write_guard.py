#!/usr/bin/env python3
"""boundary_events_write_guard.py — Claude Code PreToolUse hook (#2171).

`.claude/metrics/boundary-events.jsonl` is the plugin's boundary-level
accountability ledger (`hooks/lib/boundary_events.py`, #859) — every guard
hook's block/warn/bypass decision is recorded there, and that module's own
docstring states rows must never carry free text (command text, prompt
text, file paths, reasons), only rule IDs from closed vocabularies. A
direct `Write` or `Edit` tool call targeting that file bypasses
`emit_boundary_event()` entirely and could forge or corrupt that record
from inside the session — this hook raises the cost of that forgery the
same way `pre_tool_guard.py` raises it for other sensitive paths, by
blocking a Write/Edit whose `file_path`/`path` resolves to the ledger.

Step 1.1 of plans/2164-verdict-ledger-writer.md — Write/Edit only. Bash
write-shaped command detection and `settings.json` registration are a
separate, later step (Step 1.2) and are NOT part of this module yet.

Contract (docs/python-hook-contract.md):
    Input : PreToolUse JSON on stdin — `tool_input.file_path` or
            `tool_input.path`, resolved relative to `cwd` when not absolute
    Output: block message on stdout naming `emit_boundary_event()`
            (`hooks/lib/boundary_events.py`) as the remedy
    Exit  : 2 to block, 0 to allow. Fail-open on any exception (malformed
            payload, unreadable cwd, unresolvable repo root) — never raises.

Path matching is lexical only (`os.path.abspath` — `.`/`..` collapsing, no
symlink following): a symlink-escape sandbox is explicitly out of scope
(plan Step 1.1 TEST note) — this guard raises the cost of forgery, it does
not sandbox the filesystem.

Stdlib-only. See ADR 0014.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_HOOK_DIR = Path(__file__).resolve().parent
_LIB_DIR = _HOOK_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import artifact_paths
from boundary_events import emit_boundary_event as _emit_boundary_event
from stdin_json import read_stdin_json  # type: ignore[import-not-found]

_LEDGER_NAME = "boundary-events.jsonl"


def emit_boundary_event(*args, **kwargs) -> None:
    """Local safety net (#859): even a misbehaving helper must never affect
    this hook's exit code, stdout, or stderr."""
    try:
        _emit_boundary_event(*args, **kwargs)
    except Exception:  # noqa: BLE001, S110 - fail-open by design
        pass


def _extract_file_path(tool_input: object) -> str:
    """Return `tool_input.file_path`, `tool_input.path`, or empty string —
    mirrors `pre_tool_guard._extract_file_path`'s field-preference order."""
    if not isinstance(tool_input, dict):
        return ""
    file_path = tool_input.get("file_path")
    if isinstance(file_path, str) and file_path:
        return file_path
    other = tool_input.get("path")
    if isinstance(other, str) and other:
        return other
    return ""


def targets_ledger(file_path: str, cwd: str) -> bool:
    """True when `file_path` (joined against `cwd` if not absolute) names
    the same on-disk path `emit_boundary_event()` itself resolves and
    writes to — `artifact_paths.resolve_file("metrics", ...)` under the
    repo root, not a bare `.claude/metrics/` prefix match (so
    `review-verdicts.jsonl`, Slice 2's own store, is unaffected)."""
    if not file_path:
        return False
    base = Path(cwd) if cwd else Path.cwd()
    candidate = Path(file_path)
    if not candidate.is_absolute():
        candidate = base / candidate
    candidate_norm = os.path.abspath(str(candidate))

    ledger = artifact_paths.resolve_file(
        "metrics", _LEDGER_NAME, root=cwd, migrate=False
    )
    ledger_norm = os.path.abspath(str(ledger))

    return candidate_norm == ledger_norm


def main() -> int:
    try:
        payload = read_stdin_json()
        if payload is None:
            return 0

        file_path = _extract_file_path(payload.get("tool_input"))
        if not file_path:
            return 0

        raw_cwd = payload.get("cwd")
        cwd = (
            raw_cwd
            if isinstance(raw_cwd, str) and raw_cwd and "\0" not in raw_cwd
            else "."
        )

        if not targets_ledger(file_path, cwd):
            return 0

        raw_tool = payload.get("tool_name")
        tool = raw_tool if isinstance(raw_tool, str) and raw_tool else "Write"
        raw_session_id = payload.get("session_id")
        session_id = raw_session_id if isinstance(raw_session_id, str) else None

        emit_boundary_event(
            cwd, "boundary_events_write_guard", tool, "block", "ledger-write-blocked", session_id
        )
        print(f"BLOCKED: Direct write to '{file_path}' is not allowed.")
        print(
            "This file is the boundary-events accountability ledger (#859) — "
            "it is append-only from the session's perspective."
        )
        print(
            "Use emit_boundary_event() in plugins/dev-team/hooks/lib/boundary_events.py "
            "instead of writing to it directly."
        )
        return 2
    except Exception:  # noqa: BLE001 - fail-open by design, see module docstring
        return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
