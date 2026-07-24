#!/usr/bin/env python3
"""pre_tool_guard.py — Claude Code PreToolUse hook (Python port of pre-tool-guard.sh).

Runs before Write and Edit tool calls. Blocks writes to sensitive paths
(credentials, secrets, keys). Warns on writes to protected config files.
Enforces freeze-mode's scope lock when `freeze-state.json` sits alongside.

Input : JSON on stdin with `tool_input.file_path` or `tool_input.path`.
Output: message on stdout; exit 2 to block, exit 0 to allow.
Config: `hooks/guards.json` (same directory as the hook itself).
"""

from __future__ import annotations

import fnmatch
import json
import os
import sys
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from boundary_events import emit_boundary_event as _emit_boundary_event


def emit_boundary_event(*args, **kwargs) -> None:
    """Local safety net (#859): even a misbehaving helper must never affect
    this hook's exit code, stdout, or stderr."""
    try:
        _emit_boundary_event(*args, **kwargs)
    except Exception:  # noqa: BLE001, S110 - fail-open by design
        pass


_DEFAULT_BLOCKED = [
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*credential*",
    "*secret*",
    "*.token",
]
_DEFAULT_WARN = [
    ".claude/settings.json",
    ".claude/claude.md",
]


# ---------------------------------------------------------------------------
# stdin → file path
# ---------------------------------------------------------------------------


def _extract_file_path(raw: str) -> str:
    """Return `tool_input.file_path`, `tool_input.path`, or empty string.

    Mirrors the bash `jq -r '.tool_input.file_path // .tool_input.path // empty'`.
    """
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return ""
    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path")
    if isinstance(file_path, str) and file_path:
        return file_path
    other = tool_input.get("path")
    if isinstance(other, str) and other:
        return other
    return ""


# ---------------------------------------------------------------------------
# Glob matching — the bash uses `case ... esac`, we use fnmatch.fnmatchcase
# with matching semantics (no case folding — we lowercase subjects ourselves).
# ---------------------------------------------------------------------------


def _matches_any(subject: str, patterns: list[str]) -> bool:
    return any(
        pattern and fnmatch.fnmatchcase(subject, pattern) for pattern in patterns
    )


# ---------------------------------------------------------------------------
# Config loading — guards.json + freeze-state.json
# ---------------------------------------------------------------------------


def _load_guards(guards_path: Path) -> tuple:
    """Return (blocked_patterns, warn_patterns) from guards.json or defaults."""
    if not guards_path.is_file():
        return list(_DEFAULT_BLOCKED), list(_DEFAULT_WARN)
    try:
        data = json.loads(guards_path.read_text())
    except (OSError, ValueError):
        return list(_DEFAULT_BLOCKED), list(_DEFAULT_WARN)
    blocked = [p for p in (data.get("blocked_paths") or []) if isinstance(p, str) and p]
    warn = [p for p in (data.get("warn_paths") or []) if isinstance(p, str) and p]
    if not blocked:
        blocked = list(_DEFAULT_BLOCKED)
    if not warn:
        warn = list(_DEFAULT_WARN)
    return blocked, warn


def _load_freeze(freeze_path: Path) -> list[str] | None:
    """Return the freeze `allowed_patterns` when freeze is active, else None."""
    if not freeze_path.is_file():
        return None
    try:
        data = json.loads(freeze_path.read_text())
    except (OSError, ValueError):
        return None
    if data.get("active") is not True and data.get("active") != "true":
        return None
    allowed = [
        p for p in (data.get("allowed_patterns") or []) if isinstance(p, str) and p
    ]
    return allowed


# ---------------------------------------------------------------------------
# Guard evaluation
# ---------------------------------------------------------------------------


def evaluate(
    file_path: str,
    guards_path: Path,
    freeze_path: Path,
    cwd: str = ".",
    session_id: str | None = None,
) -> tuple:
    """Return (exit_code, [stdout_lines]) for a single file_path decision.

    - exit_code 0 with `[warning]` lines means "allow with warning".
    - exit_code 0 with `[]` means "silent pass".
    - exit_code 2 with `[block message]` means "block".

    Emits a boundary event (#859) for every warn/block decision.
    """
    if not file_path:
        return 0, []

    filename = os.path.basename(file_path)
    lower_filename = filename.lower()
    lower_path = file_path.lower()

    # Freeze mode first — scope lock trumps allow list.
    allowed = _load_freeze(freeze_path)
    if allowed is not None:
        matched = any(
            (
                fnmatch.fnmatchcase(file_path, pat)
                or fnmatch.fnmatchcase(lower_path, pat)
            )
            for pat in allowed
        )
        if not matched:
            allowed_display = "\n".join(allowed)
            emit_boundary_event(cwd, "pre_tool_guard", "Write", "block", "freeze-scope-lock", session_id)
            return 2, [
                "BLOCKED: Freeze mode is active. Only files matching the allowed patterns can be edited.",
                f"File: {file_path}",
                f"Allowed: {allowed_display}",
                "Use /unfreeze to lift the scope lock.",
            ]

    blocked_patterns, warn_patterns = _load_guards(guards_path)

    if _matches_any(lower_filename, blocked_patterns) or _matches_any(
        lower_path, blocked_patterns
    ):
        emit_boundary_event(cwd, "pre_tool_guard", "Write", "block", "sensitive-path", session_id)
        return 2, [
            f"BLOCKED: Write to '{file_path}' is not allowed.",
            "This path matches a sensitive-file pattern in .claude/hooks/guards.json.",
            "If this write is intentional, confirm with the user before proceeding.",
        ]

    if _matches_any(lower_path, warn_patterns):
        emit_boundary_event(cwd, "pre_tool_guard", "Write", "warn", "protected-config", session_id)
        return 0, [
            f"WARNING: '{file_path}' is a protected configuration file.",
            "Verify this change is intentional before writing.",
        ]

    return 0, []


def main() -> int:
    raw = sys.stdin.read()
    file_path = _extract_file_path(raw)
    if not file_path:
        return 0
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        payload = {}
    cwd = (payload.get("cwd") if isinstance(payload, dict) else None) or "."
    session_id = payload.get("session_id") if isinstance(payload, dict) else None
    script_dir = Path(__file__).resolve().parent
    exit_code, lines = evaluate(
        file_path,
        script_dir / "guards.json",
        script_dir / "freeze-state.json",
        cwd,
        session_id,
    )
    for line in lines:
        print(line)
    return exit_code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
