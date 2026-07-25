"""Unit tests for hooks/lib/artifact_paths.py (Slice 4, plan
opt-in-metrics-and-claude-scoped-artifacts.md).

Covers project_root() git-root resolution with cwd fallback.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from _repo_root import REPO_ROOT as _REPO_ROOT

_LIB_DIR = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

_TESTS_LIB = _REPO_ROOT / "plugins" / "dev-team" / "tests" / "lib"
if str(_TESTS_LIB) not in sys.path:
    sys.path.insert(0, str(_TESTS_LIB))

import artifact_paths  # type: ignore[import-not-found]
from hermetic import hermetic_git_env  # type: ignore[import-not-found]


def _init_repo(path: Path) -> dict:
    env = hermetic_git_env(home=path)
    subprocess.run(["git", "init", "-q"], cwd=path, env=env, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=path, env=env, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=path, env=env, check=True)
    return env


def test_project_root_resolves_git_toplevel(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    assert artifact_paths.project_root(start=tmp_path) == tmp_path.resolve()


def test_project_root_falls_back_to_start_outside_a_repo(tmp_path: Path) -> None:
    non_repo = tmp_path / "not-a-repo"
    non_repo.mkdir()
    assert artifact_paths.project_root(start=non_repo) == non_repo


def test_project_root_resolves_from_a_subdirectory(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    sub = tmp_path / "sub" / "deeper"
    sub.mkdir(parents=True)
    assert artifact_paths.project_root(start=sub) == tmp_path.resolve()


# --- category directory accessors -----------------------------------------


def test_metrics_dir_resolves_under_dot_claude(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    assert artifact_paths.metrics_dir(tmp_path) == tmp_path.resolve() / ".claude" / "metrics"


def test_memory_dir_resolves_under_dot_claude(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    assert artifact_paths.memory_dir(tmp_path) == tmp_path.resolve() / ".claude" / "memory"


def test_plans_dir_resolves_under_dot_claude(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    assert artifact_paths.plans_dir(tmp_path) == tmp_path.resolve() / ".claude" / "plans"
