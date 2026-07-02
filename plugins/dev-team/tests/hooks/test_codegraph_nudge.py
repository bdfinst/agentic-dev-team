"""Unit tests for hooks/codegraph_nudge.py (#593).

Mirror of tests/hooks/codegraph_nudge.bats (parallel and turn-mark hook
tests). The mark hook stays out-of-scope for this slice — only
codegraph-nudge is being ported here.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[4]
_HOOK = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "codegraph_nudge.py"
_CAREFUL_STATE = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "careful-state.json"

EXPECTED_WARN_MSG = (
    "[codegraph-nudge] CodeGraph is initialized in this project. Prefer "
    "codegraph_context or codegraph_explore for multi-file exploration; "
    "Grep/Glob/Read for confirming a specific detail."
)


@pytest.fixture(autouse=True)
def clean_careful_state():
    """Wipe careful-state.json before AND after every test. A leaked file
    silently flips the hook into block mode and corrupts every warn-path
    assertion."""
    _CAREFUL_STATE.unlink(missing_ok=True)
    yield
    _CAREFUL_STATE.unlink(missing_ok=True)


def _run(payload: dict, extra_env: dict = None) -> subprocess.CompletedProcess[str]:
    proc_env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        "PYTHONDONTWRITEBYTECODE": "1",
        **(extra_env or {}),
    }
    return subprocess.run(
        ["python3", str(_HOOK)],
        input=json.dumps(payload),
        env=proc_env,
        capture_output=True,
        text=True,
        check=False,
    )


def _write_transcript(path: Path, user_count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f'{{"type":"user","message":"u{i}"}}' for i in range(user_count)]
    path.write_text("\n".join(lines) + ("\n" if lines else ""))


# --- Step 1: silent when .codegraph is absent -----------------------------


def test_silent_when_codegraph_absent(tmp_path: Path) -> None:
    r = _run(
        {
            "tool_name": "Read",
            "cwd": str(tmp_path),
            "tool_input": {"file_path": str(tmp_path / "foo.txt")},
        }
    )
    assert r.returncode == 0
    assert r.stdout == ""
    assert r.stderr == ""


# --- Step 2: Read is always single-file → silent --------------------------


def test_silent_on_read_when_codegraph_present(tmp_path: Path) -> None:
    (tmp_path / ".codegraph").mkdir()
    (tmp_path / "foo.txt").write_text("hi")
    r = _run(
        {
            "tool_name": "Read",
            "cwd": str(tmp_path),
            "tool_input": {"file_path": str(tmp_path / "foo.txt")},
        }
    )
    assert r.returncode == 0
    assert r.stdout == ""
    assert r.stderr == ""


# --- Step 3: Grep/Glob heuristic -----------------------------------------


def test_warns_on_grep_with_directory_path(tmp_path: Path) -> None:
    (tmp_path / ".codegraph").mkdir()
    (tmp_path / "src").mkdir()
    r = _run(
        {
            "tool_name": "Grep",
            "cwd": str(tmp_path),
            "tool_input": {"pattern": "foo", "path": str(tmp_path / "src")},
        }
    )
    assert r.returncode == 0
    assert r.stderr.strip() == EXPECTED_WARN_MSG


def test_silent_on_grep_with_file_path(tmp_path: Path) -> None:
    (tmp_path / ".codegraph").mkdir()
    (tmp_path / "foo.txt").write_text("hi")
    r = _run(
        {
            "tool_name": "Grep",
            "cwd": str(tmp_path),
            "tool_input": {"pattern": "foo", "path": str(tmp_path / "foo.txt")},
        }
    )
    assert r.returncode == 0
    assert r.stderr == ""


def test_warns_on_glob_with_wildcard_pattern(tmp_path: Path) -> None:
    (tmp_path / ".codegraph").mkdir()
    r = _run(
        {
            "tool_name": "Glob",
            "cwd": str(tmp_path),
            "tool_input": {"pattern": "**/*.ts"},
        }
    )
    assert r.returncode == 0
    assert r.stderr.strip() == EXPECTED_WARN_MSG


def test_silent_on_glob_with_literal_pattern(tmp_path: Path) -> None:
    (tmp_path / ".codegraph").mkdir()
    r = _run(
        {
            "tool_name": "Glob",
            "cwd": str(tmp_path),
            "tool_input": {"pattern": "package.json"},
        }
    )
    assert r.returncode == 0
    assert r.stderr == ""


# --- Step 4: sentinel-based turn detection -------------------------------


def test_silent_after_codegraph_used_this_turn(tmp_path: Path) -> None:
    (tmp_path / ".codegraph").mkdir()
    (tmp_path / ".claude").mkdir()
    (tmp_path / "src").mkdir()
    tx = tmp_path / "transcripts" / "abc123.jsonl"
    _write_transcript(tx, 3)
    (tmp_path / ".claude" / "codegraph-turn-state.json").write_text(
        json.dumps({"transcript_id": "abc123", "turn_counter": 3})
    )
    r = _run(
        {
            "tool_name": "Grep",
            "cwd": str(tmp_path),
            "transcript_path": str(tx),
            "tool_input": {"pattern": "foo", "path": str(tmp_path / "src")},
        }
    )
    assert r.returncode == 0
    assert r.stderr == ""


def test_warns_when_sentinel_is_for_prior_turn(tmp_path: Path) -> None:
    (tmp_path / ".codegraph").mkdir()
    (tmp_path / ".claude").mkdir()
    (tmp_path / "src").mkdir()
    tx = tmp_path / "transcripts" / "abc123.jsonl"
    _write_transcript(tx, 4)
    (tmp_path / ".claude" / "codegraph-turn-state.json").write_text(
        json.dumps({"transcript_id": "abc123", "turn_counter": 3})
    )
    r = _run(
        {
            "tool_name": "Grep",
            "cwd": str(tmp_path),
            "transcript_path": str(tx),
            "tool_input": {"pattern": "foo", "path": str(tmp_path / "src")},
        }
    )
    assert r.returncode == 0
    assert r.stderr.strip() == EXPECTED_WARN_MSG


def test_warns_when_sentinel_is_for_different_transcript(tmp_path: Path) -> None:
    (tmp_path / ".codegraph").mkdir()
    (tmp_path / ".claude").mkdir()
    (tmp_path / "src").mkdir()
    tx = tmp_path / "transcripts" / "abc123.jsonl"
    _write_transcript(tx, 2)
    (tmp_path / ".claude" / "codegraph-turn-state.json").write_text(
        json.dumps({"transcript_id": "other", "turn_counter": 2})
    )
    r = _run(
        {
            "tool_name": "Grep",
            "cwd": str(tmp_path),
            "transcript_path": str(tx),
            "tool_input": {"pattern": "foo", "path": str(tmp_path / "src")},
        }
    )
    assert r.returncode == 0
    assert r.stderr.strip() == EXPECTED_WARN_MSG


def test_warns_when_sentinel_missing(tmp_path: Path) -> None:
    (tmp_path / ".codegraph").mkdir()
    (tmp_path / ".claude").mkdir()
    (tmp_path / "src").mkdir()
    tx = tmp_path / "transcripts" / "abc123.jsonl"
    _write_transcript(tx, 1)
    r = _run(
        {
            "tool_name": "Grep",
            "cwd": str(tmp_path),
            "transcript_path": str(tx),
            "tool_input": {"pattern": "foo", "path": str(tmp_path / "src")},
        }
    )
    assert r.returncode == 0
    assert r.stderr.strip() == EXPECTED_WARN_MSG


# --- Step 5: careful-mode escalation --------------------------------------


def test_blocks_in_careful_mode(tmp_path: Path) -> None:
    (tmp_path / ".codegraph").mkdir()
    (tmp_path / "src").mkdir()
    _CAREFUL_STATE.write_text(json.dumps({"active": True}))
    try:
        r = _run(
            {
                "tool_name": "Grep",
                "cwd": str(tmp_path),
                "tool_input": {"pattern": "foo", "path": str(tmp_path / "src")},
            }
        )
        assert r.returncode == 2
        assert r.stderr.strip() == f"{EXPECTED_WARN_MSG} [blocked by /careful]"
    finally:
        _CAREFUL_STATE.unlink(missing_ok=True)


def test_warns_when_careful_inactive(tmp_path: Path) -> None:
    (tmp_path / ".codegraph").mkdir()
    (tmp_path / "src").mkdir()
    _CAREFUL_STATE.write_text(json.dumps({"active": False}))
    try:
        r = _run(
            {
                "tool_name": "Grep",
                "cwd": str(tmp_path),
                "tool_input": {"pattern": "foo", "path": str(tmp_path / "src")},
            }
        )
        assert r.returncode == 0
        assert r.stderr.strip() == EXPECTED_WARN_MSG
    finally:
        _CAREFUL_STATE.unlink(missing_ok=True)


# --- Step 6: fail-open guards ---------------------------------------------


def test_fails_open_on_malformed_json() -> None:
    r = subprocess.run(
        ["python3", str(_HOOK)],
        input="not json",
        env={
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0
    assert r.stdout == ""
    assert r.stderr == ""


def test_fails_open_on_empty_stdin() -> None:
    r = subprocess.run(
        ["python3", str(_HOOK)],
        input="",
        env={
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0


def test_fails_open_on_missing_transcript(tmp_path: Path) -> None:
    """Nonexistent transcript_path falls through — sentinel logic returns
    'not used', so the warn fires. Same as bats' fails_open_on_missing_transcript."""
    (tmp_path / ".codegraph").mkdir()
    (tmp_path / "src").mkdir()
    r = _run(
        {
            "tool_name": "Grep",
            "cwd": str(tmp_path),
            "transcript_path": "/nonexistent/transcript.jsonl",
            "tool_input": {"pattern": "foo", "path": str(tmp_path / "src")},
        }
    )
    assert r.returncode == 0
    assert r.stderr.strip() == EXPECTED_WARN_MSG


def test_pass_silently_on_unrelated_tool(tmp_path: Path) -> None:
    (tmp_path / ".codegraph").mkdir()
    r = _run(
        {"tool_name": "Bash", "cwd": str(tmp_path), "tool_input": {"command": "ls"}}
    )
    assert r.returncode == 0
    assert r.stderr == ""
