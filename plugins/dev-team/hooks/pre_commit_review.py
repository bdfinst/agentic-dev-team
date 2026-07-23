#!/usr/bin/env python3
"""pre_commit_review — Claude Code PreToolUse:Bash hook (Python port).

Python port of hooks/pre-commit-review.sh (#583 / #572 Cluster B).
Extended under #709 to require and durably log a reason when the
`--no-verify`/`-n` bypass is used, closing the frictionless-bypass gap
identified by the gate-correlation evidence (bypassed commits correlate
with materially higher rework).

Blocks `git commit` (exit 2) unless a `.review-passed` file exists in
cwd with a hash matching the currently staged content. The /code-review
command auto-scopes to uncommitted changes and writes this file when
review passes.

Non-commit Bash commands pass through immediately (exit 0).
`git commit --no-verify` (or bare `-n`) is still allowed through — but
only when the process environment carries a non-empty `GATE_BYPASS_REASON`.
When present, the bypass is appended as one line to
`metrics/gate-bypass-audit.jsonl` (unconditional — not gated by
`DEV_TEAM_TELEMETRY`) and the commit proceeds. When absent, the commit is
blocked with a message naming `GATE_BYPASS_REASON` as the required
mechanism.

Contract (docs/python-hook-contract.md):
    Input : JSON on stdin (Claude Code PreToolUse:Bash payload)
    Exit 0: allow the tool call
    Exit 2: block the tool call (feedback returned to Claude on stdout,
            mirrored to stderr — some hook-error wrappers only surface
            stderr, and a stdout-only block message was going unseen)

Stdlib-only. Python 3.8+.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional


_HOOK_DIR = Path(__file__).resolve().parent
_LIB_DIR = _HOOK_DIR / "lib"

sys.path.insert(0, str(_LIB_DIR))
try:
    from pre_commit_detect import (  # type: ignore[import-not-found]
        bypass_flag_name,
        has_bypass_flag,
        is_git_commit_command,
    )
    from review_gate_hash import review_gate_hash  # type: ignore[import-not-found]
    from stdin_json import read_stdin_json  # type: ignore[import-not-found]
    from boundary_events import (  # type: ignore[import-not-found]
        emit_boundary_event as _emit_boundary_event,
    )
except ImportError:  # pragma: no cover

    def is_git_commit_command(_: str) -> bool:  # type: ignore[misc]
        return False

    def has_bypass_flag(_: str) -> bool:  # type: ignore[misc]
        return False

    def bypass_flag_name(_: str) -> Optional[str]:  # type: ignore[misc]
        return None

    def review_gate_hash(cwd=None) -> str:  # type: ignore[misc]
        return ""

    def read_stdin_json() -> Optional[dict]:  # type: ignore[misc]
        return None

    def _emit_boundary_event(*_args, **_kwargs) -> None:  # type: ignore[misc]
        return None


def emit_boundary_event(*args, **kwargs) -> None:
    """Local safety net (#859): even a misbehaving helper must never affect
    this hook's exit code, stdout, or stderr."""
    try:
        _emit_boundary_event(*args, **kwargs)
    except Exception:  # noqa: BLE001 - fail-open by design
        pass


_BLOCK_MESSAGE = (
    "BLOCKED: Code review required before committing.\n"
    "\n"
    "Run /code-review to review staged files.\n"
    "If review passes, the commit will be allowed on the next attempt.\n"
    "\n"
    "To bypass: use git commit --no-verify\n"
)

_BYPASS_BLOCK_MESSAGE = (
    "BLOCKED: git commit --no-verify (or -n) requires a reason.\n"
    "\n"
    "Set GATE_BYPASS_REASON to a non-empty explanation and retry, e.g.:\n"
    '  GATE_BYPASS_REASON="hotfix, review to follow" git commit --no-verify -m ...\n'
    "\n"
    "The bypass is logged to metrics/gate-bypass-audit.jsonl once a reason\n"
    "is supplied.\n"
)


def _emit_block(message: str) -> None:
    """Write a block message to both stdout and stderr (#1367).

    Stdout stays the canonical UI channel; stderr is mirrored because some
    hook-error wrappers surface only stderr on a nonzero hook exit.
    """
    sys.stdout.write(message)
    sys.stderr.write(message)


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


def _current_branch() -> str:
    try:
        completed = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            check=False,
            text=True,
        )
    except (FileNotFoundError, OSError):
        return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def _plugin_version() -> str:
    manifest = _HOOK_DIR / ".." / ".claude-plugin" / "plugin.json"
    try:
        data = json.loads(manifest.read_text())
        version = data.get("version")
        if isinstance(version, str) and version:
            return version
    except (OSError, ValueError):
        pass
    return "unknown"


def _record_bypass_audit(flag: str, reason: str, staged_count: int) -> None:
    """Append one accountability line to metrics/gate-bypass-audit.jsonl.

    Unconditional (not gated by DEV_TEAM_TELEMETRY) — mirrors the existing
    metrics/override-audit.jsonl precedent for a bypass a human/agent
    actively chose, not passive usage telemetry.
    """
    audit_log_path = Path("metrics") / "gate-bypass-audit.jsonl"
    entry = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "branch": _current_branch(),
        "triggeredBy": flag,
        "reason": reason,
        "stagedFileCount": staged_count,
        "pluginVersion": _plugin_version(),
    }
    audit_log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(audit_log_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, separators=(",", ":")) + "\n")


def main() -> int:
    payload = read_stdin_json()
    if payload is None:
        return 0

    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0
    command = str(tool_input.get("command") or "")

    cwd = payload.get("cwd") or "."
    session_id = payload.get("session_id")

    if not is_git_commit_command(command):
        return 0

    staged = _staged_names()
    # Nothing staged → nothing to gate.
    if not staged:
        return 0

    if has_bypass_flag(command):
        flag = bypass_flag_name(command) or "--no-verify"
        reason = os.environ.get("GATE_BYPASS_REASON", "").strip()
        if reason:
            _record_bypass_audit(flag, reason, len(staged))
            emit_boundary_event(
                cwd, "pre_commit_review", "Bash", "bypass", flag, session_id
            )
            return 0
        _emit_block(_BYPASS_BLOCK_MESSAGE)
        return 2

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
    _emit_block(_BLOCK_MESSAGE)
    emit_boundary_event(
        cwd, "pre_commit_review", "Bash", "block", "pre-commit-review", session_id
    )
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
