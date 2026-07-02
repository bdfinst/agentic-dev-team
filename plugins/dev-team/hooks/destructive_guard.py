#!/usr/bin/env python3
"""Python port of hooks/destructive-guard.sh (#598 / #572 Phase 3).

Claude Code PreToolUse hook. Runs before Bash tool calls, detects
destructive commands, and either warns (default, exit 0) or blocks (when
careful mode is active, exit 2). Patterns are loaded from
`hooks/destructive-commands.json`; careful state from
`hooks/careful-state.json`. Falls back to inline defaults if either config
is absent.

Contract (docs/python-hook-contract.md):
    Input : PreToolUse JSON on stdin with tool_input.command
    Output: exit 0 = allow (optionally with CAUTION warning on stdout)
            exit 2 = block; stdout contains the block message

Stdlib-only (json/pathlib/sys). Python 3.8+. See ADR 0014.

Refs: #572 (bash → Python migration epic).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List, Optional, Tuple


_SCRIPT_DIR = Path(__file__).resolve().parent
_COMMANDS_FILE = _SCRIPT_DIR / "destructive-commands.json"
_CAREFUL_FILE = _SCRIPT_DIR / "careful-state.json"


# Inline fallbacks — kept in the exact order the .sh's here-docs use so
# the "first match wins" ordering is preserved byte-for-byte across
# implementations.
_DEFAULT_FILE_PATTERNS = ["rm -rf", "rm -r", "rm -fr"]
_DEFAULT_DB_PATTERNS = ["drop table", "drop database", "truncate"]
_DEFAULT_GIT_PATTERNS = [
    "git push --force",
    "git push -f",
    "git reset --hard",
    "git clean -f",
    "git clean -fd",
    "git checkout -- .",
    "git branch -D",
]
_DEFAULT_PROCESS_PATTERNS = ["kill -9", "killall", "pkill"]
_DEFAULT_PERMISSION_PATTERNS = ["chmod 777"]
_DEFAULT_SAFE_PATTERNS = [
    "rm -rf node_modules",
    "rm -rf dist",
    "rm -rf build",
    "rm -rf .cache",
    "rm -rf coverage",
    "rm -rf tmp",
    "rm -rf __pycache__",
]


def _read_stdin() -> str:
    try:
        return sys.stdin.read()
    except (OSError, ValueError):
        return ""


def _load_json(path: Path) -> Optional[dict]:
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _load_input(raw: str) -> dict:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _extract_command(payload: dict) -> str:
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return ""
    cmd = tool_input.get("command") or ""
    return cmd if isinstance(cmd, str) else ""


def _careful_active() -> bool:
    """Read careful-state.json's `active` boolean. False on any error."""
    data = _load_json(_CAREFUL_FILE)
    if data is None:
        return False
    value = data.get("active")
    if isinstance(value, bool):
        return value
    # The .sh treats `.active // false` as false when missing; string
    # values other than "true" (bash string comparison) are treated as
    # false. Match that here.
    return isinstance(value, str) and value == "true"


def _load_patterns() -> Tuple[
    List[str], List[str], List[str], List[str], List[str], List[str]
]:
    """Load pattern lists from the config file, falling back to inline defaults.

    Return order: (file, db, git, process, permission, safe).
    """
    data = _load_json(_COMMANDS_FILE)
    if data is None:
        return (
            list(_DEFAULT_FILE_PATTERNS),
            list(_DEFAULT_DB_PATTERNS),
            list(_DEFAULT_GIT_PATTERNS),
            list(_DEFAULT_PROCESS_PATTERNS),
            list(_DEFAULT_PERMISSION_PATTERNS),
            list(_DEFAULT_SAFE_PATTERNS),
        )

    def _list_of_str(key: str) -> List[str]:
        raw = data.get(key)
        if not isinstance(raw, list):
            return []
        return [x for x in raw if isinstance(x, str)]

    return (
        _list_of_str("file_destruction"),
        _list_of_str("database_destruction"),
        _list_of_str("git_destruction"),
        _list_of_str("process_destruction"),
        _list_of_str("permission_escalation"),
        _list_of_str("safe_allowlist"),
    )


def _matches_any(cmd_lower: str, patterns: List[str]) -> Optional[str]:
    """Return the first pattern whose lowercase substring appears in `cmd_lower`."""
    for pattern in patterns:
        if not pattern:
            continue
        # The .sh does `case "$cmd" in *"$pattern"*)` — a plain substring
        # match. Both operands are already lowercased.
        if pattern.lower() in cmd_lower:
            return pattern
    return None


def _first_match(cmd_lower: str, groups: List[Tuple[List[str], str]]) -> Optional[str]:
    """Iterate groups in .sh order, return 'category: pattern' on first hit."""
    for patterns, category in groups:
        pattern = _matches_any(cmd_lower, patterns)
        if pattern is not None:
            return f"{category}: {pattern}"
    return None


def _emit(text: str) -> None:
    """Print with trailing newline — matches the .sh's `echo` behavior."""
    sys.stdout.write(text + "\n")


def main() -> int:
    raw = _read_stdin()
    payload = _load_input(raw)
    command = _extract_command(payload)
    if not command:
        return 0

    lower_command = command.lower()

    file_pat, db_pat, git_pat, proc_pat, perm_pat, safe_pat = _load_patterns()

    # Safe allowlist short-circuit — matches the .sh's `matches_safe` check.
    if _matches_any(lower_command, safe_pat) is not None:
        return 0

    match = _first_match(
        lower_command,
        [
            (file_pat, "File destruction"),
            (db_pat, "Database destruction"),
            (git_pat, "Git destruction"),
            (proc_pat, "Process destruction"),
            (perm_pat, "Permission escalation"),
        ],
    )
    if match is None:
        return 0

    careful = _careful_active()
    if careful:
        _emit(f"BLOCKED: Destructive command detected ({match}).")
        _emit(f"Command: {command}")
        _emit("Careful mode is active. This command has been blocked.")
        _emit("Use /careful off to disable careful mode, or confirm with the user.")
        return 2

    _emit(f"CAUTION: Destructive command detected ({match}).")
    _emit(f"Command: {command}")
    _emit("This action is hard to reverse. Confirm with the user before proceeding.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
