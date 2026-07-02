"""Unit tests for hooks/codegraph_bootstrap.py (#592).

Mirror of tests/hooks/codegraph_bootstrap.bats one-for-one.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[4]
_HOOK = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "codegraph_bootstrap.py"

_BUILD_MSG = (
    "[codegraph-bootstrap] This project uses CodeGraph but has no local index yet"
)
_INSTALL_MSG = "[codegraph-bootstrap] This project uses CodeGraph but it is not installed on this machine"


@pytest.fixture
def fake_codegraph(tmp_path: Path) -> Path:
    """A fake `codegraph` binary that `codegraph init` creates the db."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "codegraph"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        '[ "${1:-}" = "init" ] && touch "$PWD/.codegraph/codegraph.db"\n'
        "exit 0\n"
    )
    fake.chmod(0o755)
    return fake


def _run(payload: dict, env: dict, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    proc_env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(tmp_path),
        "TMPDIR": str(tmp_path),
        "PYTHONDONTWRITEBYTECODE": "1",
        **env,
    }
    return subprocess.run(
        ["python3", str(_HOOK)],
        input=json.dumps(payload),
        env=proc_env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_no_codegraph_dir_silent_noop(tmp_path: Path) -> None:
    case = tmp_path / "case"
    case.mkdir()
    r = _run(
        {"hook_event_name": "SessionStart", "cwd": str(case)}, env={}, tmp_path=tmp_path
    )
    assert r.returncode == 0
    assert r.stdout == ""
    assert r.stderr == ""


def test_index_already_present_silent_noop(
    tmp_path: Path, fake_codegraph: Path
) -> None:
    case = tmp_path / "case"
    (case / ".codegraph").mkdir(parents=True)
    (case / ".codegraph" / "codegraph.db").touch()
    r = _run(
        {"hook_event_name": "SessionStart", "cwd": str(case)},
        env={"CODEGRAPH_BIN": str(fake_codegraph)},
        tmp_path=tmp_path,
    )
    assert r.returncode == 0
    assert r.stdout == ""
    assert r.stderr == ""


def test_binary_present_builds_index_sync(tmp_path: Path, fake_codegraph: Path) -> None:
    case = tmp_path / "case"
    (case / ".codegraph").mkdir(parents=True)
    r = _run(
        {"hook_event_name": "SessionStart", "cwd": str(case)},
        env={"CODEGRAPH_BIN": str(fake_codegraph), "CODEGRAPH_BOOTSTRAP_SYNC": "1"},
        tmp_path=tmp_path,
    )
    assert r.returncode == 0
    assert (case / ".codegraph" / "codegraph.db").is_file()
    assert _BUILD_MSG in r.stderr


def test_binary_missing_prints_install_nudge(tmp_path: Path) -> None:
    case = tmp_path / "case"
    (case / ".codegraph").mkdir(parents=True)
    r = _run(
        {"hook_event_name": "SessionStart", "cwd": str(case)},
        env={"CODEGRAPH_BIN": "/nonexistent/codegraph"},
        tmp_path=tmp_path,
    )
    assert r.returncode == 0
    assert not (case / ".codegraph" / "codegraph.db").exists()
    assert _INSTALL_MSG in r.stderr


def test_db_file_env_override_used_for_present_check(
    tmp_path: Path, fake_codegraph: Path
) -> None:
    case = tmp_path / "case"
    (case / ".codegraph").mkdir(parents=True)
    alt = case / ".codegraph" / "custom.db"
    alt.touch()
    r = _run(
        {"hook_event_name": "SessionStart", "cwd": str(case)},
        env={"CODEGRAPH_DB_FILE": str(alt), "CODEGRAPH_BIN": str(fake_codegraph)},
        tmp_path=tmp_path,
    )
    assert r.returncode == 0
    assert r.stdout == ""
    assert r.stderr == ""


def test_malformed_stdin_fails_open_silent(tmp_path: Path) -> None:
    proc_env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(tmp_path),
        "TMPDIR": str(tmp_path),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    r = subprocess.run(
        ["python3", str(_HOOK)],
        input="not json",
        env=proc_env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0
    assert r.stdout == ""
    assert r.stderr == ""


def test_missing_cwd_falls_back_to_pwd(tmp_path: Path) -> None:
    """No .codegraph in PWD fallback → silent no-op."""
    case = tmp_path / "case-no-codegraph"
    case.mkdir()
    proc_env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(tmp_path),
        "TMPDIR": str(tmp_path),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    r = subprocess.run(
        ["python3", str(_HOOK)],
        input=json.dumps({"hook_event_name": "SessionStart"}),
        env=proc_env,
        cwd=str(case),
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0
    assert r.stdout == ""
    assert r.stderr == ""


def test_empty_stdin_silent_noop(tmp_path: Path) -> None:
    proc_env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(tmp_path),
        "TMPDIR": str(tmp_path),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    r = subprocess.run(
        ["python3", str(_HOOK)],
        input="",
        env=proc_env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0
