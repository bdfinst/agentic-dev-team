"""Pytest tests for mutation_kill_shared.py — cross-language loop mechanics
shared between mutation_kill_loop.py (C#) and mutation_kill_loop_python.py
(Python/mutmut) (#1583).

git_revert/git_reset_and_revert/git_commit and _timeout_from_env already have
extensive indirect coverage through both loops' own test suites (each
monkeypatches ``loop.subprocess.run``/``loop.subprocess.TimeoutExpired``,
which are the real, shared ``subprocess`` module objects, so those tests
already exercise THIS module's implementation directly — see
test_mutation_kill_loop.py and test_mutation_kill_loop_python.py). This file
adds direct, module-local coverage for ``stop_reason`` (new in #1583, no
prior direct test) plus a small argv-shape sanity check per git function so
this module has its own test suite independent of either loop's.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from _mutation_test_helpers import SCRIPTS_DIR

sys.path.insert(0, str(SCRIPTS_DIR))

import mutation_kill_shared as shared


# =============================================================================
# stop_reason — the "no improvement across rounds" stop predicate
# =============================================================================
def test_stop_reason_is_none_when_survivors_remain_and_no_prior_round():
    assert shared.stop_reason(3, None) is None


def test_stop_reason_is_none_when_survivor_count_improved():
    assert shared.stop_reason(2, 5) is None


def test_stop_reason_flags_zero_survivors_as_done():
    assert shared.stop_reason(0, None) == "no survivors — done"


def test_stop_reason_flags_zero_survivors_as_done_even_with_a_prior_round():
    assert shared.stop_reason(0, 4) == "no survivors — done"


def test_stop_reason_flags_no_improvement_when_count_is_unchanged():
    assert shared.stop_reason(3, 3) == "no improvement this round — stopping"


def test_stop_reason_flags_no_improvement_when_count_got_worse():
    assert shared.stop_reason(4, 3) == "no improvement this round — stopping"


# =============================================================================
# _timeout_from_env — parser both loops (and mutation_kill_headless.py's
# generation timeout) rely on.
# =============================================================================
def test_timeout_from_env_returns_the_default_when_unset(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("SOME_SHARED_TIMEOUT_VAR", raising=False)
    assert shared._timeout_from_env("SOME_SHARED_TIMEOUT_VAR", 42) == 42


def test_timeout_from_env_parses_an_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SOME_SHARED_TIMEOUT_VAR", "99")
    assert shared._timeout_from_env("SOME_SHARED_TIMEOUT_VAR", 42) == 99


def test_timeout_from_env_rejects_a_non_numeric_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SOME_SHARED_TIMEOUT_VAR", "not-a-number")
    with pytest.raises(ValueError, match="SOME_SHARED_TIMEOUT_VAR"):
        shared._timeout_from_env("SOME_SHARED_TIMEOUT_VAR", 42)


def test_timeout_from_env_rejects_a_non_positive_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SOME_SHARED_TIMEOUT_VAR", "0")
    with pytest.raises(ValueError, match="positive"):
        shared._timeout_from_env("SOME_SHARED_TIMEOUT_VAR", 42)


# =============================================================================
# git_revert / git_reset_and_revert / git_commit — argv shape (behavioral
# coverage, including timeouts and real-git integrity scenarios, lives in
# both loops' own test suites — see this file's module docstring).
# =============================================================================
def test_git_revert_checks_out_only_the_given_file(tmp_path: Path, monkeypatch):
    class _R:
        returncode = 0

    seen: list = []

    def fake_run(argv, **k):
        seen.append(argv)
        return _R()

    monkeypatch.setattr(shared.subprocess, "run", fake_run)

    shared.git_revert(tmp_path / "Foo.txt")

    assert seen[0] == ["git", "--literal-pathspecs", "checkout", "--", str(tmp_path / "Foo.txt")]


def test_git_reset_and_revert_resets_then_checks_out(tmp_path: Path, monkeypatch):
    class _R:
        returncode = 0

    calls: list = []

    def fake_run(argv, **k):
        calls.append(argv)
        return _R()

    monkeypatch.setattr(shared.subprocess, "run", fake_run)

    assert shared.git_reset_and_revert(tmp_path / "Foo.txt") is True
    assert [c[2] for c in calls] == ["reset", "checkout"]


def test_git_commit_stages_then_commits_only_the_given_file(tmp_path: Path, monkeypatch):
    class _R:
        returncode = 0

    calls: list = []

    def fake_run(argv, **k):
        calls.append(argv)
        return _R()

    monkeypatch.setattr(shared.subprocess, "run", fake_run)

    assert shared.git_commit("msg", tmp_path / "Foo.txt") is True
    assert calls[0] == ["git", "--literal-pathspecs", "add", "--", str(tmp_path / "Foo.txt")]
    assert calls[1] == [
        "git",
        "--literal-pathspecs",
        "commit",
        "-m",
        "msg",
        "--",
        str(tmp_path / "Foo.txt"),
    ]
