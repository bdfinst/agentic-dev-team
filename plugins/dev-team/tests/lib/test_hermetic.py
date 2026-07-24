"""Unit tests for tests/lib/hermetic.py's hermetic_git_env() (issue #715)."""

from __future__ import annotations

import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parent
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

import hermetic  # type: ignore[import-not-found]

_DANGEROUS = (
    "GIT_DIR",
    "GIT_INDEX_FILE",
    "GIT_WORK_TREE",
    "GIT_PREFIX",
    "GIT_REFLOG_ACTION",
)


def test_strips_dangerous_git_vars_even_when_ambient(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "decoy.git"))
    monkeypatch.setenv("GIT_INDEX_FILE", str(tmp_path / "decoy-index"))
    monkeypatch.setenv("GIT_WORK_TREE", str(tmp_path / "decoy-wt"))
    monkeypatch.setenv("GIT_PREFIX", "subdir/")
    monkeypatch.setenv("GIT_REFLOG_ACTION", "push")

    env = hermetic.hermetic_git_env()

    for var in _DANGEROUS:
        assert var not in env


def test_redirects_git_config_to_dev_null() -> None:
    env = hermetic.hermetic_git_env()
    assert env["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert env["GIT_CONFIG_SYSTEM"] == "/dev/null"


def test_home_override_when_provided(tmp_path: Path) -> None:
    env = hermetic.hermetic_git_env(home=tmp_path)
    assert env["HOME"] == str(tmp_path)


def test_home_left_as_ambient_when_not_provided(monkeypatch) -> None:
    monkeypatch.setenv("HOME", "/original/home")
    env = hermetic.hermetic_git_env()
    assert env["HOME"] == "/original/home"


def test_preserves_path_for_git_lookup() -> None:
    env = hermetic.hermetic_git_env()
    assert "PATH" in env
