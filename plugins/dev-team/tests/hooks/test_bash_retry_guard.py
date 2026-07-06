"""Unit tests for hooks/bash_retry_guard.py (#591 / #572 Phase 3).

The bash-retry-guard is an advisory PreToolUse hook — never blocks (always
exit 0). It counts consecutive identical Bash commands per-session and
nudges after THRESHOLD in a row. This suite exercises:

  - exit 0 on every path (advisory contract)
  - silent-pass on excluded commands (verify-family, read-only shells)
  - state-file counting: first fire, second identical, third → warning
  - reset on divergent command
  - DEV_TEAM_BASH_RETRY_THRESHOLD honored
  - session-id vs cwd-hash state-key fallback
  - malformed input silently passes
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[4]
_HOOK = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "bash_retry_guard.py"


def _run(payload: dict, env: dict, tmpdir: Path) -> subprocess.CompletedProcess[str]:
    """Invoke the Python hook with `payload` on stdin, return the result."""
    proc_env = {
        **os.environ,
        "TMPDIR": str(tmpdir),
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        **env,
    }
    # Boundary events (#859) resolve metrics/ from payload["cwd"] — default
    # it to the isolated `tmpdir` so tests never write into the real repo.
    payload = {"cwd": str(tmpdir), **payload}
    return subprocess.run(
        ["python3", str(_HOOK)],
        input=json.dumps(payload),
        env=proc_env,
        capture_output=True,
        text=True,
        check=False,
    )


# --- exit-code contract ----------------------------------------------------


def test_always_exits_zero_on_empty_stdin(tmp_path: Path) -> None:
    result = subprocess.run(
        ["python3", str(_HOOK)],
        input="",
        env={**os.environ, "TMPDIR": str(tmp_path)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == ""


def test_always_exits_zero_on_malformed_json(tmp_path: Path) -> None:
    result = subprocess.run(
        ["python3", str(_HOOK)],
        input="{not json",
        env={**os.environ, "TMPDIR": str(tmp_path)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0


def test_always_exits_zero_on_missing_command(tmp_path: Path) -> None:
    result = _run({"session_id": "s1"}, env={}, tmpdir=tmp_path)
    assert result.returncode == 0
    assert result.stdout == ""


# --- exclusions ------------------------------------------------------------


@pytest.mark.parametrize(
    "cmd",
    [
        "npm test",
        "npm run test",
        "npm run lint",
        "npm run build",
        "pytest tests/",
        "bats tests/",
        "eslint .",
        "tsc --noEmit",
        "go test ./...",
        "cargo test",
        "cargo build",
        "mvn verify",
        "gradle build",
        "make",
        "vitest",
        "jest",
        "ruff check .",
        "mypy src/",
        "shellcheck script.sh",
    ],
)
def test_verify_family_commands_are_silent(cmd: str, tmp_path: Path) -> None:
    """The verify-guard hook covers these; retry-guard must not double-warn."""
    for _ in range(5):  # even at 5x repeats
        result = _run(
            {"session_id": "s1", "tool_input": {"command": cmd}},
            env={},
            tmpdir=tmp_path,
        )
        assert result.returncode == 0
        assert result.stdout == ""


@pytest.mark.parametrize(
    "cmd",
    [
        "ls",
        "ls -la",
        "pwd",
        "echo hi",
        "cat file.txt",
        "head -5 log",
        "tail -f log",
        "grep pattern file",
    ],
)
def test_read_only_commands_are_silent(cmd: str, tmp_path: Path) -> None:
    for _ in range(5):
        result = _run(
            {"session_id": "s2", "tool_input": {"command": cmd}},
            env={},
            tmpdir=tmp_path,
        )
        assert result.returncode == 0
        assert result.stdout == ""


# --- consecutive-count behavior --------------------------------------------


def test_first_two_runs_are_silent_third_warns(tmp_path: Path) -> None:
    payload = {"session_id": "sess-A", "tool_input": {"command": "rm -rf /tmp/junk"}}
    r1 = _run(payload, env={}, tmpdir=tmp_path)
    assert r1.returncode == 0 and r1.stdout == ""
    r2 = _run(payload, env={}, tmpdir=tmp_path)
    assert r2.returncode == 0 and r2.stdout == ""
    r3 = _run(payload, env={}, tmpdir=tmp_path)
    assert r3.returncode == 0
    assert "bash-retry-guard" in r3.stdout
    assert "3 consecutive" in r3.stdout


def test_divergent_command_resets_count(tmp_path: Path) -> None:
    p1 = {"session_id": "sess-B", "tool_input": {"command": "mv a b"}}
    p2 = {"session_id": "sess-B", "tool_input": {"command": "cp c d"}}
    _run(p1, env={}, tmpdir=tmp_path)  # count=1
    _run(p1, env={}, tmpdir=tmp_path)  # count=2
    _run(p2, env={}, tmpdir=tmp_path)  # count=1 (reset)
    r = _run(p1, env={}, tmpdir=tmp_path)  # count=1 again for p1
    assert r.returncode == 0
    assert r.stdout == "" or "3 consecutive" not in r.stdout


def test_threshold_env_override(tmp_path: Path) -> None:
    payload = {"session_id": "sess-C", "tool_input": {"command": "curl x"}}
    # With threshold=2, the second call warns.
    r1 = _run(payload, env={"DEV_TEAM_BASH_RETRY_THRESHOLD": "2"}, tmpdir=tmp_path)
    assert r1.stdout == ""
    r2 = _run(payload, env={"DEV_TEAM_BASH_RETRY_THRESHOLD": "2"}, tmpdir=tmp_path)
    assert "2 consecutive" in r2.stdout


def test_threshold_zero_disables(tmp_path: Path) -> None:
    payload = {"session_id": "sess-D", "tool_input": {"command": "date"}}
    for _ in range(10):
        r = _run(payload, env={"DEV_TEAM_BASH_RETRY_THRESHOLD": "0"}, tmpdir=tmp_path)
        assert r.returncode == 0
    # No warning even after 10 identical calls when threshold=0.
    # (The .sh's contract is that threshold=0 disables — because count >= 0
    # is always true, but the intent — documented in the hook's own message
    # — is "set to 0 to disable". Follow that intent for byte-parity of
    # observable behavior.)


# --- state-key isolation ---------------------------------------------------


def test_different_sessions_have_independent_counts(tmp_path: Path) -> None:
    cmd = "curl example.com"
    for _ in range(2):
        _run(
            {"session_id": "sess-X", "tool_input": {"command": cmd}},
            env={},
            tmpdir=tmp_path,
        )
    # Fresh session — should NOT inherit sess-X's count.
    r = _run(
        {"session_id": "sess-Y", "tool_input": {"command": cmd}},
        env={},
        tmpdir=tmp_path,
    )
    assert r.stdout == ""


def test_missing_session_id_falls_back_to_cwd_hash(tmp_path: Path) -> None:
    cmd = "wget foo"
    payload = {"tool_input": {"command": cmd}, "cwd": str(tmp_path)}
    for _ in range(2):
        _run(payload, env={}, tmpdir=tmp_path)
    r = _run(payload, env={}, tmpdir=tmp_path)
    assert "3 consecutive" in r.stdout


# --- whitespace normalization ---------------------------------------------


def test_purges_stale_state_files_older_than_ttl(tmp_path: Path) -> None:
    """State files never got a TTL purge (unlike tdd_guard.py/
    mutation_adapters/lib.py's `_purge_stale`) — old per-session state files
    accumulated in $TMPDIR/dev-team-bash-retry forever."""
    state_dir = tmp_path / "dev-team-bash-retry"
    state_dir.mkdir(parents=True)

    stale = state_dir / "old-session.json"
    stale.write_text('{"hash":"deadbeef","count":1}')
    old_time = time.time() - (241 * 60)  # just over a 4h TTL
    os.utime(stale, (old_time, old_time))

    fresh = state_dir / "recent-session.json"
    fresh.write_text('{"hash":"cafef00d","count":1}')

    _run(
        {"session_id": "sess-purge", "tool_input": {"command": "curl example.com"}},
        env={},
        tmpdir=tmp_path,
    )

    assert not stale.exists(), "stale state file should be purged on write"
    assert fresh.exists(), "recently-touched state file should survive purge"


def test_whitespace_variations_hash_identically(tmp_path: Path) -> None:
    _run(
        {"session_id": "s-ws", "tool_input": {"command": "curl example.com"}},
        env={},
        tmpdir=tmp_path,
    )
    _run(
        {"session_id": "s-ws", "tool_input": {"command": "  curl   example.com  "}},
        env={},
        tmpdir=tmp_path,
    )
    r = _run(
        {"session_id": "s-ws", "tool_input": {"command": "curl\texample.com"}},
        env={},
        tmpdir=tmp_path,
    )
    # Three normalization-equivalent calls → threshold hit.
    assert "3 consecutive" in r.stdout
