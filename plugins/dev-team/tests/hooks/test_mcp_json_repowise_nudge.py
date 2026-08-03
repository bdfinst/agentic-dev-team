"""Unit tests for hooks/mcp_json_repowise_nudge.py (#1747).

SessionStart hook that suggests running /project-init when .mcp.json is
git-tracked and carries a repowise entry (the exact case its
hooks/lib/mcp_json_repowise.py::relocate() companion can fix). Fail-open,
never blocks a session.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from _repo_root import REPO_ROOT as _REPO_ROOT

_HOOK = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "mcp_json_repowise_nudge.py"

_TESTS_LIB = Path(__file__).resolve().parents[2] / "tests" / "lib"
if str(_TESTS_LIB) not in sys.path:
    sys.path.insert(0, str(_TESTS_LIB))

from hermetic import hermetic_git_env  # type: ignore[import-not-found]

_REPOWISE_ENTRY = {
    "command": "repowise",
    "args": ["mcp", "/Users/alice/Dev/some-repo", "--transport", "stdio"],
}


def _run(cwd: Path) -> subprocess.CompletedProcess[str]:
    payload = {"hook_event_name": "SessionStart", "cwd": str(cwd)}
    return subprocess.run(
        ["python3", str(_HOOK)],
        input=json.dumps(payload),
        env=hermetic_git_env(home=cwd),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=hermetic_git_env(home=cwd),
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo(cwd: Path) -> None:
    _git(cwd, "init", "-q")
    _git(cwd, "config", "user.email", "test@example.com")
    _git(cwd, "config", "user.name", "Test")


def _write_mcp_json(cwd: Path, data: dict) -> None:
    (cwd / ".mcp.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _commit_all(cwd: Path, message: str) -> None:
    _git(cwd, "add", "-A")
    _git(cwd, "commit", "-q", "-m", message)


def _commit_placeholder(cwd: Path) -> None:
    (cwd / "README.md").write_text("placeholder\n", encoding="utf-8")
    _commit_all(cwd, "init")


def test_no_payload_is_silent(tmp_path: Path) -> None:
    r = subprocess.run(
        ["python3", str(_HOOK)],
        input="",
        env=hermetic_git_env(home=tmp_path),
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0
    assert r.stdout == ""


def test_silent_when_no_mcp_json(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _commit_placeholder(tmp_path)
    r = _run(tmp_path)
    assert r.returncode == 0
    assert r.stdout == ""


def test_silent_when_mcp_json_untracked(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _commit_placeholder(tmp_path)
    _write_mcp_json(tmp_path, {"mcpServers": {"repowise": _REPOWISE_ENTRY}})
    r = _run(tmp_path)
    assert r.returncode == 0
    assert r.stdout == ""


def test_silent_when_tracked_without_repowise_entry(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_mcp_json(tmp_path, {"mcpServers": {"codegraph": {"command": "codegraph"}}})
    _commit_all(tmp_path, "add mcp.json")
    r = _run(tmp_path)
    assert r.returncode == 0
    assert r.stdout == ""


def test_nudges_when_tracked_with_repowise_entry(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_mcp_json(tmp_path, {"mcpServers": {"repowise": _REPOWISE_ENTRY}})
    _commit_all(tmp_path, "add mcp.json")
    r = _run(tmp_path)
    assert r.returncode == 0
    assert "/project-init" in r.stdout
    assert "repowise" in r.stdout
