"""Pytest tests for hooks/verify_guard.py (#608 / #572 Phase 3; escalated to
a hard block for stuck loops by #708).

Covers: verify-class command detection, threshold-based warning/block,
state persistence via TMPDIR, session-id fallback to cksum-of-cwd,
threshold override via env, the edit-since-last-verify signal written by
verify_guard_edit_marker.py, and silent-pass on non-verify commands /
malformed input.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from _repo_root import REPO_ROOT as _REPO_ROOT

_HOOKS_DIR = _REPO_ROOT / "plugins" / "dev-team" / "hooks"
_HOOK_PY = _HOOKS_DIR / "verify_guard.py"
_EDIT_MARKER_PY = _HOOKS_DIR / "verify_guard_edit_marker.py"


def _run(payload: dict, *, tmp: Path, threshold: str | None = None):
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": "C.UTF-8",
        "TMPDIR": str(tmp),
    }
    if threshold is not None:
        env["DEV_TEAM_VERIFY_THRESHOLD"] = threshold
    # Boundary events (#859) resolve metrics/ from payload["cwd"] — default
    # it to the isolated `tmp` dir so tests never write into the real repo.
    payload = {"cwd": str(tmp), **payload}
    return subprocess.run(
        [sys.executable, str(_HOOK_PY)],
        input=json.dumps(payload).encode(),
        env=env,
        capture_output=True,
        timeout=10,
        check=False,
    )


def _run_edit_marker(payload: dict, *, tmp: Path):
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": "C.UTF-8",
        "TMPDIR": str(tmp),
    }
    payload = {"cwd": str(tmp), **payload}
    return subprocess.run(
        [sys.executable, str(_EDIT_MARKER_PY)],
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


def test_third_identical_call_with_no_edits_between_blocks(tmp_path: Path) -> None:
    """AC1: the same command run 3x consecutively with zero intervening
    Edit/Write/NotebookEdit calls is a genuinely stuck loop — block it."""
    payload = {"session_id": "sX", "tool_input": {"command": "npm test"}}
    for _ in range(2):
        _run(payload, tmp=tmp_path)
    r = _run(payload, tmp=tmp_path)
    assert r.returncode == 2
    assert b"[BLOCK]" in r.stdout
    assert b"verify-guard: This verify command has run 3" in r.stdout
    assert b"DEV_TEAM_VERIFY_THRESHOLD=0" in r.stdout


def test_third_identical_call_with_edit_between_does_not_block(tmp_path: Path) -> None:
    """AC2: the normal RED/GREEN/REFACTOR pattern — the same command re-run
    3x, but with a real edit before each repeat — must never block."""
    payload = {"session_id": "sY", "tool_input": {"command": "npm test"}}
    r = _run(payload, tmp=tmp_path)
    assert r.returncode == 0
    assert r.stdout == b""

    _run_edit_marker({"session_id": "sY"}, tmp=tmp_path)
    r = _run(payload, tmp=tmp_path)
    assert r.returncode == 0
    assert r.stdout == b""

    _run_edit_marker({"session_id": "sY"}, tmp=tmp_path)
    r = _run(payload, tmp=tmp_path)
    assert r.returncode == 0
    assert r.stdout == b""


def test_edit_between_only_some_repeats_still_blocks_once_they_go_unbroken(
    tmp_path: Path,
) -> None:
    """An edit resets the counter; 3 unbroken repeats AFTER the edit still
    trip the block — the edit signal isn't a permanent bypass."""
    payload = {"session_id": "sZ", "tool_input": {"command": "pytest -q"}}
    _run(payload, tmp=tmp_path)
    _run_edit_marker({"session_id": "sZ"}, tmp=tmp_path)
    r1 = _run(payload, tmp=tmp_path)
    assert r1.returncode == 0
    r2 = _run(payload, tmp=tmp_path)
    assert r2.returncode == 0
    r3 = _run(payload, tmp=tmp_path)
    assert r3.returncode == 2
    assert b"[BLOCK]" in r3.stdout


def test_threshold_zero_suppresses_block_but_still_warns(tmp_path: Path) -> None:
    """AC3: DEV_TEAM_VERIFY_THRESHOLD=0 continues to suppress the block —
    the advisory-only legacy behavior (warn on every run) is unchanged."""
    payload = {"session_id": "s0", "tool_input": {"command": "pytest"}}
    r = _run(payload, tmp=tmp_path, threshold="0")
    assert r.returncode == 0
    assert b"consecutive times" in r.stdout
    assert b"[BLOCK]" not in r.stdout


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


# --- verify_guard_edit_marker.py (#708) --------------------------------------


def test_edit_marker_silent_and_exits_zero(tmp_path: Path) -> None:
    r = _run_edit_marker({"session_id": "m1", "cwd": str(tmp_path)}, tmp=tmp_path)
    assert r.returncode == 0
    assert r.stdout == b""


def test_edit_marker_malformed_stdin_silent(tmp_path: Path) -> None:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "TMPDIR": str(tmp_path),
    }
    r = subprocess.run(
        [sys.executable, str(_EDIT_MARKER_PY)],
        input=b"{broken",
        env=env,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert r.returncode == 0
    assert r.stdout == b""


def test_edit_marker_stamps_shared_state_file(tmp_path: Path) -> None:
    """The marker hook sets `edited: true` on the same state file
    verify_guard.py reads/writes for the same session."""
    _run(
        {"session_id": "m2", "tool_input": {"command": "npm test"}},
        tmp=tmp_path,
    )
    _run_edit_marker({"session_id": "m2"}, tmp=tmp_path)
    state = tmp_path / "dev-team-verify-guard" / "m2.json"
    data = json.loads(state.read_text())
    assert data["edited"] is True
    # hash/count from the prior verify_guard.py run are preserved.
    assert data["count"] == 1


def test_edit_marker_before_first_verify_run_is_a_harmless_no_op(
    tmp_path: Path,
) -> None:
    """Marking an edit before any verify command has run must not itself
    trigger a block or crash the next verify_guard.py invocation."""
    _run_edit_marker({"session_id": "m3"}, tmp=tmp_path)
    r = _run(
        {"session_id": "m3", "tool_input": {"command": "npm test"}},
        tmp=tmp_path,
    )
    assert r.returncode == 0
    assert r.stdout == b""
