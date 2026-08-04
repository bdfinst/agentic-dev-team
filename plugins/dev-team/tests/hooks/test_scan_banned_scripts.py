"""Unit tests for hooks/scan_banned_scripts.py (#1755).

PostToolUse working-tree backstop for scan_bash_for_banned_scripts.py — runs
after EVERY tool call and inspects `git status --porcelain`, so it catches a
banned-extension file under plugins/dev-team/ regardless of which tool
created it (the PreToolUse half only scans Bash command strings).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_TESTS_LIB = _REPO_ROOT / "plugins" / "dev-team" / "tests" / "lib"
if str(_TESTS_LIB) not in sys.path:
    sys.path.insert(0, str(_TESTS_LIB))

from hermetic import hermetic_git_env  # type: ignore[import-not-found]

_HOOK = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "scan_banned_scripts.py"


def _run(cwd: Path, env: dict) -> subprocess.CompletedProcess[str]:
    payload = {"hook_event_name": "PostToolUse", "tool_name": "Write", "cwd": str(cwd)}
    return subprocess.run(
        [sys.executable, str(_HOOK)],
        input=json.dumps(payload),
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def repo(tmp_path: Path) -> tuple[Path, dict]:
    """A hermetic git repo with the plugins/dev-team/ dir already present."""
    env = hermetic_git_env(home=tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, env=env, check=True)
    (tmp_path / "plugins" / "dev-team" / "hooks").mkdir(parents=True)
    (tmp_path / "plugins" / "dev-team" / "hooks" / "keep.py").write_text("pass\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "seed"], cwd=tmp_path, env=env, check=True)
    return tmp_path, env


def test_passes_clean_repo(repo: tuple[Path, dict]) -> None:
    cwd, env = repo
    result = _run(cwd, env)
    assert result.returncode == 0


def test_blocks_untracked_banned_file(repo: tuple[Path, dict]) -> None:
    cwd, env = repo
    (cwd / "plugins" / "dev-team" / "hooks" / "rogue.sh").write_text("echo hi\n")
    result = _run(cwd, env)
    assert result.returncode == 2
    assert "plugins/dev-team/hooks/rogue.sh" in result.stdout
    assert "plugins/dev-team/hooks/rogue.sh" in result.stderr
    assert result.stdout.startswith("[BLOCK]")


def test_blocks_staged_banned_file(repo: tuple[Path, dict]) -> None:
    cwd, env = repo
    (cwd / "plugins" / "dev-team" / "hooks" / "rogue.bat").write_text("echo hi\n")
    subprocess.run(
        ["git", "add", "plugins/dev-team/hooks/rogue.bat"], cwd=cwd, env=env, check=True
    )
    result = _run(cwd, env)
    assert result.returncode == 2
    assert "rogue.bat" in result.stdout


def test_ignores_banned_file_outside_plugin_scope(repo: tuple[Path, dict]) -> None:
    cwd, env = repo
    (cwd / "scripts").mkdir()
    (cwd / "scripts" / "dev-setup.sh").write_text("echo hi\n")
    result = _run(cwd, env)
    assert result.returncode == 0


def test_allows_install_sh_carveout(repo: tuple[Path, dict]) -> None:
    cwd, env = repo
    (cwd / "plugins" / "dev-team" / "install.sh").write_text("echo hi\n")
    result = _run(cwd, env)
    assert result.returncode == 0


def test_allows_py_sh_carveout(repo: tuple[Path, dict]) -> None:
    cwd, env = repo
    (cwd / "plugins" / "dev-team" / "hooks" / "py.sh").write_text("echo hi\n")
    result = _run(cwd, env)
    assert result.returncode == 0


def test_ignores_untracked_python_file(repo: tuple[Path, dict]) -> None:
    cwd, env = repo
    (cwd / "plugins" / "dev-team" / "hooks" / "new_module.py").write_text("pass\n")
    result = _run(cwd, env)
    assert result.returncode == 0


def test_not_a_git_repo_passes_open(tmp_path: Path) -> None:
    (tmp_path / "plugins" / "dev-team" / "hooks").mkdir(parents=True)
    (tmp_path / "plugins" / "dev-team" / "hooks" / "rogue.sh").write_text("echo hi\n")
    result = _run(tmp_path, {**hermetic_git_env(home=tmp_path)})
    assert result.returncode == 0


def test_blocks_renamed_destination(repo: tuple[Path, dict]) -> None:
    cwd, env = repo
    (cwd / "plugins" / "dev-team" / "hooks" / "old_name.py").write_text("pass\n")
    subprocess.run(
        ["git", "add", "plugins/dev-team/hooks/old_name.py"], cwd=cwd, env=env, check=True
    )
    subprocess.run(
        ["git", "commit", "-q", "-m", "add old_name.py"], cwd=cwd, env=env, check=True
    )
    subprocess.run(
        [
            "git",
            "mv",
            "plugins/dev-team/hooks/old_name.py",
            "plugins/dev-team/hooks/new_name.sh",
        ],
        cwd=cwd,
        env=env,
        check=True,
    )
    result = _run(cwd, env)
    assert result.returncode == 2
    assert "plugins/dev-team/hooks/new_name.sh" in result.stdout
