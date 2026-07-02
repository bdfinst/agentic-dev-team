"""Unit tests for hooks/pre_commit_review.py (#583).

Behavior parity with hooks/pre-commit-review.sh — the review gate that
blocks `git commit` unless a `.review-passed` file with a matching
staged-content hash exists in cwd. Content hashing is delegated to the
ported review_gate_hash module (#576).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[4]
_HOOK = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "pre_commit_review.py"

_TESTS_LIB = Path(__file__).resolve().parents[2] / "tests" / "lib"
if str(_TESTS_LIB) not in sys.path:
    sys.path.insert(0, str(_TESTS_LIB))

from hermetic import hermetic_git_env  # type: ignore[import-not-found]  # noqa: E402


def _run(payload: dict, cwd: Path) -> subprocess.CompletedProcess[str]:
    proc_env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
    }
    return subprocess.run(
        ["python3", str(_HOOK)],
        input=json.dumps(payload),
        env=proc_env,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A minimal hermetic git repo with one staged file."""
    env = hermetic_git_env(home=tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t"], cwd=tmp_path, env=env, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "t"], cwd=tmp_path, env=env, check=True
    )
    (tmp_path / "a.ts").write_text("v1\n")
    subprocess.run(["git", "add", "a.ts"], cwd=tmp_path, env=env, check=True)
    return tmp_path


def _current_hash(repo: Path) -> str:
    """Compute the review-gate hash via the Python lib (authoritative)."""
    import sys as _sys

    lib_dir = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"
    if str(lib_dir) not in _sys.path:
        _sys.path.insert(0, str(lib_dir))
    import review_gate_hash as _rgh  # type: ignore[import-not-found]

    return _rgh.review_gate_hash(cwd=repo)


# --- non-gate branches ----------------------------------------------------


def test_non_commit_silent(repo: Path) -> None:
    r = _run({"tool_name": "Bash", "tool_input": {"command": "ls -la"}}, cwd=repo)
    assert r.returncode == 0
    assert r.stdout == ""


def test_no_verify_bypass(repo: Path) -> None:
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit --no-verify -m x"}},
        cwd=repo,
    )
    assert r.returncode == 0


def test_commit_with_nothing_staged_silent(tmp_path: Path) -> None:
    """No staged files → nothing to gate."""
    env = hermetic_git_env(home=tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t"], cwd=tmp_path, env=env, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "t"], cwd=tmp_path, env=env, check=True
    )
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}},
        cwd=tmp_path,
    )
    assert r.returncode == 0


def test_malformed_stdin_silent() -> None:
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


# --- gate branches --------------------------------------------------------


def test_missing_gate_file_blocks(repo: Path) -> None:
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, cwd=repo
    )
    assert r.returncode == 2
    assert "BLOCKED" in r.stdout
    assert "/code-review" in r.stdout
    assert "--no-verify" in r.stdout


def test_matching_gate_file_passes_and_is_consumed(repo: Path) -> None:
    h = _current_hash(repo)
    (repo / ".review-passed").write_text(h)
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, cwd=repo
    )
    assert r.returncode == 0
    # Gate file consumed on success.
    assert not (repo / ".review-passed").exists()


def test_stale_gate_file_blocks(repo: Path) -> None:
    """Reviewed content changed → hash mismatch → block. Gate file NOT removed."""
    h = _current_hash(repo)
    (repo / ".review-passed").write_text(h)
    # Edit the staged file's content.
    (repo / "a.ts").write_text("v2-unreviewed\n")
    env = hermetic_git_env(home=repo)
    subprocess.run(["git", "add", "a.ts"], cwd=repo, env=env, check=True)
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, cwd=repo
    )
    assert r.returncode == 2
    assert "BLOCKED" in r.stdout
    # Gate file preserved because it did NOT match.
    assert (repo / ".review-passed").exists()


def test_extra_staged_file_after_review_blocks(repo: Path) -> None:
    h = _current_hash(repo)
    (repo / ".review-passed").write_text(h)
    (repo / "b.ts").write_text("new\n")
    env = hermetic_git_env(home=repo)
    subprocess.run(["git", "add", "b.ts"], cwd=repo, env=env, check=True)
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, cwd=repo
    )
    assert r.returncode == 2
