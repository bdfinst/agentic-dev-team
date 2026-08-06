"""Pytest tests for hooks/destructive_guard.py.

Drives main() via subprocess with representative PreToolUse JSON payloads,
covering both the blocked path (careful mode active + a destructive
command) and the pass-through path (non-destructive command, and the
always-allowed safe-allowlist entries).

`_careful_active()` resolves careful-state.json per invoking repo via
`hooks/lib/artifact_paths.py`'s `resolve_file()`, keyed off the payload's
own `cwd` (issue #1900, same fix pattern as #1890's freeze-state.json) —
NOT a fixed path relative to the hook's own script directory. Each test
below writes that file under its own private `tmp_path`, passed as the
payload's `cwd`, so tests never share one physical file across the suite
and need no cross-test/cross-file locking.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from _repo_root import REPO_ROOT as _REPO_ROOT

_HOOK_PY = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "destructive_guard.py"


def _run(payload: dict, cwd: Path) -> subprocess.CompletedProcess:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": "C.UTF-8",
    }
    payload = {"cwd": str(cwd), **payload}
    return subprocess.run(
        [sys.executable, str(_HOOK_PY)],
        input=json.dumps(payload).encode(),
        env=env,
        cwd=str(cwd),
        capture_output=True,
        timeout=10,
        check=False,
    )


def _write_careful_state(cwd: Path, active: bool) -> None:
    careful_dir = cwd / ".claude" / "hooks"
    careful_dir.mkdir(parents=True, exist_ok=True)
    (careful_dir / "careful-state.json").write_text(
        json.dumps({"active": active}), encoding="utf-8"
    )


def test_destructive_command_blocked_when_careful_active(tmp_path: Path) -> None:
    """A destructive command with careful mode active must exit 2 and
    print a BLOCKED decision."""
    _write_careful_state(tmp_path, True)

    r = _run({"tool_input": {"command": "rm -rf /"}}, tmp_path)

    assert r.returncode == 2
    assert b"BLOCKED" in r.stdout
    assert b"Destructive command detected" in r.stdout


def test_benign_command_passes_through(tmp_path: Path) -> None:
    """A non-destructive command must exit 0 with no output, careful mode
    or not."""
    r = _run({"tool_input": {"command": "ls -la"}}, tmp_path)

    assert r.returncode == 0
    assert r.stdout == b""


def test_safe_allowlisted_command_passes_through_even_when_careful(
    tmp_path: Path,
) -> None:
    """Safe-allowlist entries (e.g. `rm -rf node_modules`) short-circuit
    before the destructive check, even with careful mode active."""
    _write_careful_state(tmp_path, True)

    r = _run({"tool_input": {"command": "rm -rf node_modules"}}, tmp_path)

    assert r.returncode == 0
    assert r.stdout == b""


def test_destructive_command_warns_without_blocking_when_careful_inactive(
    tmp_path: Path,
) -> None:
    """Without careful mode, a destructive command still exits 0 (advisory
    CAUTION only, not a block). `tmp_path` is outside the real repo checkout
    so the branch-escalation probes (#862) can't resolve HEAD to the
    default branch and hard-block this regardless of careful mode."""
    r = _run({"tool_input": {"command": "git push --force"}}, tmp_path)

    assert r.returncode == 0
    assert b"CAUTION" in r.stdout


def test_missing_command_silent(tmp_path: Path) -> None:
    r = _run({"tool_input": {}}, tmp_path)
    assert r.returncode == 0
    assert r.stdout == b""


def test_malformed_stdin_silent() -> None:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    r = subprocess.run(
        [sys.executable, str(_HOOK_PY)],
        input=b"{broken",
        env=env,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert r.returncode == 0
    assert r.stdout == b""
