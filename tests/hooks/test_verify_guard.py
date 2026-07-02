"""Pytest tests for hooks/verify_guard.py (#608 / #572 Phase 3).

Covers: verify-class command detection, threshold-based warning, state
persistence via TMPDIR, session-id fallback to cksum-of-cwd, threshold
override via env, and silent-pass on non-verify commands / malformed
input.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HOOK_PY = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "verify_guard.py"


def _run(payload: dict, *, tmp: Path, threshold: str | None = None):
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": "C.UTF-8",
        "TMPDIR": str(tmp),
    }
    if threshold is not None:
        env["DEV_TEAM_VERIFY_THRESHOLD"] = threshold
    return subprocess.run(
        [sys.executable, str(_HOOK_PY)],
        input=json.dumps(payload).encode(),
        env=env,
        capture_output=True,
        timeout=10,
        check=False,
    )


def test_non_verify_command_silent(tmp_path: Path) -> None:
    r = _run({"tool_input": {"command": "ls -la"}}, tmp=tmp_path)
    assert r.returncode == 0
    assert r.stdout == b""


def test_first_verify_call_silent(tmp_path: Path) -> None:
    r = _run(
        {"session_id": "s", "tool_input": {"command": "npm test"}},
        tmp=tmp_path,
    )
    assert r.returncode == 0
    assert r.stdout == b""


def test_third_identical_call_warns(tmp_path: Path) -> None:
    payload = {"session_id": "sX", "tool_input": {"command": "npm test"}}
    for _ in range(2):
        _run(payload, tmp=tmp_path)
    r = _run(payload, tmp=tmp_path)
    assert r.returncode == 0
    assert b"verify-guard: This verify command has run 3" in r.stdout
    assert b"DEV_TEAM_VERIFY_THRESHOLD=0" in r.stdout


def test_different_command_resets_counter(tmp_path: Path) -> None:
    _run({"session_id": "s", "tool_input": {"command": "npm test"}}, tmp=tmp_path)
    _run({"session_id": "s", "tool_input": {"command": "npm test"}}, tmp=tmp_path)
    # Different command — resets.
    r = _run({"session_id": "s", "tool_input": {"command": "pytest -q"}}, tmp=tmp_path)
    assert r.stdout == b""
    # And two more identical — 3rd should warn.
    _run({"session_id": "s", "tool_input": {"command": "pytest -q"}}, tmp=tmp_path)
    r = _run({"session_id": "s", "tool_input": {"command": "pytest -q"}}, tmp=tmp_path)
    assert b"3 consecutive times" in r.stdout


def test_whitespace_normalized(tmp_path: Path) -> None:
    """`npm  test` and `npm test` are the same command."""
    for cmd in ["npm test", "npm   test", "  npm test  "]:
        _run({"session_id": "sN", "tool_input": {"command": cmd}}, tmp=tmp_path)
    # After 3 calls with normalized-identical commands, threshold hit.
    r = _run({"session_id": "sN", "tool_input": {"command": "npm test"}}, tmp=tmp_path)
    assert b"consecutive times" in r.stdout


def test_threshold_override(tmp_path: Path) -> None:
    payload = {"session_id": "s", "tool_input": {"command": "pytest"}}
    r = _run(payload, tmp=tmp_path, threshold="1")
    assert b"1 consecutive" in r.stdout


def test_threshold_zero_always_warns(tmp_path: Path) -> None:
    """Bash's `-ge 0` fires the warning on every run when THRESHOLD=0 — the
    docstring is misleading but that IS the .sh behavior. Port matches."""
    payload = {"session_id": "s", "tool_input": {"command": "pytest"}}
    r = _run(payload, tmp=tmp_path, threshold="0")
    assert b"consecutive times" in r.stdout


def test_missing_command_silent(tmp_path: Path) -> None:
    r = _run({"session_id": "s", "tool_input": {}}, tmp=tmp_path)
    assert r.returncode == 0
    assert r.stdout == b""


def test_malformed_stdin_silent(tmp_path: Path) -> None:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "TMPDIR": str(tmp_path),
    }
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


def test_state_file_written(tmp_path: Path) -> None:
    _run(
        {"session_id": "state-test", "tool_input": {"command": "npm test"}},
        tmp=tmp_path,
    )
    state = tmp_path / "dev-team-verify-guard" / "state-test.json"
    assert state.is_file()
    data = json.loads(state.read_text())
    assert data["count"] == 1
    assert isinstance(data["hash"], str) and data["hash"]


def test_session_id_missing_falls_back_to_cwd_cksum(tmp_path: Path) -> None:
    """Without session_id, the state key derives from cwd cksum; two runs
    from the same cwd should share state."""
    for _ in range(3):
        _run({"cwd": str(tmp_path), "tool_input": {"command": "pytest"}}, tmp=tmp_path)
    # The 3rd run above should have warned; verify one more warns.
    r = _run({"cwd": str(tmp_path), "tool_input": {"command": "pytest"}}, tmp=tmp_path)
    assert b"consecutive times" in r.stdout
