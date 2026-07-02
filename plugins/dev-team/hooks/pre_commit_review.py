#!/usr/bin/env python3
"""pre_commit_review — Claude Code PreToolUse:Bash hook (Python port).

Python port of hooks/pre-commit-review.sh (#583 / #572 Cluster B).

Blocks `git commit` (exit 2) unless a `.review-passed` file exists in
cwd with a hash matching the currently staged content. The /code-review
command auto-scopes to uncommitted changes and writes this file when
review passes.

Non-commit Bash commands pass through immediately (exit 0).
`git commit --no-verify` is allowed through (standard bypass).

Contract (docs/python-hook-contract.md):
    Input : JSON on stdin (Claude Code PreToolUse:Bash payload)
    Exit 0: allow the tool call
    Exit 2: block the tool call (feedback returned to Claude on stdout)

Stdlib-only. Python 3.8+.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional


_HOOK_DIR = Path(__file__).resolve().parent
_LIB_DIR = _HOOK_DIR / "lib"

sys.path.insert(0, str(_LIB_DIR))
try:
    from pre_commit_detect import is_git_commit_invocation  # type: ignore[import-not-found]
    from review_gate_hash import review_gate_hash  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover

    def is_git_commit_invocation(_: str) -> bool:  # type: ignore[misc]
        return False

    def review_gate_hash(cwd=None) -> str:  # type: ignore[misc]
        return ""


_BLOCK_MESSAGE = (
    "BLOCKED: Code review required before committing.\n"
    "\n"
    "Run /code-review to review staged files.\n"
    "If review passes, the commit will be allowed on the next attempt.\n"
    "\n"
    "To bypass: use git commit --no-verify\n"
)


def _read_stdin_json() -> Optional[dict]:
    try:
        raw = sys.stdin.read()
    except OSError:
        return None
    if not raw.strip():
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _staged_names() -> List[str]:
    try:
        completed = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            check=False,
            text=True,
        )
    except (FileNotFoundError, OSError):
        return []
    if completed.returncode != 0:
        return []
    return [line for line in completed.stdout.splitlines() if line]


def main() -> int:
    payload = _read_stdin_json()
    if payload is None:
        return 0

    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0
    command = str(tool_input.get("command") or "")

    if not is_git_commit_invocation(command):
        return 0

    # Nothing staged → nothing to gate.
    if not _staged_names():
        return 0

    current_hash = review_gate_hash()

    gate_file = Path(".review-passed")
    if gate_file.is_file():
        try:
            stored = gate_file.read_text().strip()
        except OSError:
            stored = ""
        if stored and stored == current_hash:
            # Review passed for these exact files — consume + allow.
            try:
                gate_file.unlink()
            except OSError:
                pass
            return 0

    # Block. Message goes to stdout (matching the .sh's `printf` — the .sh
    # writes to stdout, not stderr, so Claude sees it in the tool-call
    # feedback stream).
    sys.stdout.write(_BLOCK_MESSAGE)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
