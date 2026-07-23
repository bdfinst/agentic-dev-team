"""Pytest tests for hooks/destructive_guard.py.

Drives main() via subprocess with representative PreToolUse JSON payloads,
covering both the blocked path (careful mode active + a destructive
command) and the pass-through path (non-destructive command, and the
always-allowed safe-allowlist entries).

`_careful_active()` reads a fixed path (hooks/careful-state.json) rather
than an env-overridable location, so the blocked-path test writes that file
directly — mirroring the precedent already established in
plugins/dev-team/tests/hooks/test_code_intelligence_nudge.py's `clean_careful_state`
fixture. A leaked file would silently flip every other test into block
mode, so the fixture wipes it before AND after every test.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HOOK_PY = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "destructive_guard.py"
_CAREFUL_STATE = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "careful-state.json"

# Boundary events (#859) resolve metrics/ from payload["cwd"] (falling back
# to the process's actual OS cwd when absent) — isolate every subprocess run
# to a scratch dir so tests never write metrics/boundary-events.jsonl into
# the real repo checkout.
_BOUNDARY_EVENTS_SCRATCH_CWD = tempfile.mkdtemp(prefix="dev-team-destructive-guard-test-")


@pytest.fixture(autouse=True)
def clean_careful_state():
    _CAREFUL_STATE.unlink(missing_ok=True)
    yield
    _CAREFUL_STATE.unlink(missing_ok=True)


def _run(payload: dict) -> subprocess.CompletedProcess:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": "C.UTF-8",
    }
    payload = {"cwd": _BOUNDARY_EVENTS_SCRATCH_CWD, **payload}
    return subprocess.run(
        [sys.executable, str(_HOOK_PY)],
        input=json.dumps(payload).encode(),
        env=env,
        capture_output=True,
        timeout=10,
        check=False,
    )


def test_destructive_command_blocked_when_careful_active() -> None:
    """A destructive command with careful mode active must exit 2 and
    print a BLOCKED decision."""
    _CAREFUL_STATE.write_text(json.dumps({"active": True}), encoding="utf-8")

    r = _run({"tool_input": {"command": "rm -rf /"}})

    assert r.returncode == 2
    assert b"BLOCKED" in r.stdout
    assert b"Destructive command detected" in r.stdout


def test_benign_command_passes_through() -> None:
    """A non-destructive command must exit 0 with no output, careful mode
    or not."""
    r = _run({"tool_input": {"command": "ls -la"}})

    assert r.returncode == 0
    assert r.stdout == b""


def test_safe_allowlisted_command_passes_through_even_when_careful() -> None:
    """Safe-allowlist entries (e.g. `rm -rf node_modules`) short-circuit
    before the destructive check, even with careful mode active."""
    _CAREFUL_STATE.write_text(json.dumps({"active": True}), encoding="utf-8")

    r = _run({"tool_input": {"command": "rm -rf node_modules"}})

    assert r.returncode == 0
    assert r.stdout == b""


def test_destructive_command_warns_without_blocking_when_careful_inactive() -> None:
    """Without careful mode, a destructive command still exits 0 (advisory
    CAUTION only, not a block)."""
    r = _run({"tool_input": {"command": "git push --force"}})

    assert r.returncode == 0
    assert b"CAUTION" in r.stdout


def test_missing_command_silent() -> None:
    r = _run({"tool_input": {}})
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
