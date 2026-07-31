"""Pytest tests for mutation_kill_shared.py — cross-language loop mechanics
shared between mutation_kill_loop.py (C#) and mutation_kill_loop_python.py
(Python/mutmut) (#1583).

The full git_revert/git_reset_and_revert/git_commit behavioral suite
(timeout handling, argv shape, add/commit/reset branch coverage) lives here
as the single source of truth (#1603). It was previously triplicated
near-verbatim across test_mutation_kill_loop_verify.py (C#) and
test_mutation_kill_loop_python.py (Python) despite both loops sharing this
exact implementation since #1583 — a behavior change to any of these three
functions required updating assertions in up to three files to stay in sync.
Both loop test files now carry only an identity check (``assert loop.git_revert
is mutation_kill_shared.git_revert``, etc.) plus whatever integration coverage
is genuinely loop-specific (e.g. the Python loop's real-git hermetic
regression tests, which exercise these same functions against a real repo
rather than a mocked ``subprocess.run``).
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
# git_revert / git_reset_and_revert / git_commit — argv shape.
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


def test_git_commit_returns_false_on_a_non_timeout_commit_failure(
    tmp_path: Path, monkeypatch
):
    """git_commit's own commit-leg failure branch (a non-zero returncode with
    no timeout involved — e.g. "nothing to commit") — direct coverage, not
    just the timeout variant already covered elsewhere (#1563 gap 2)."""

    class _R:
        def __init__(self, returncode):
            self.returncode = returncode

    calls: list = []

    def fake_run(argv, **k):
        calls.append(argv)
        return _R(0) if len(calls) == 1 else _R(1)

    monkeypatch.setattr(shared.subprocess, "run", fake_run)

    assert shared.git_commit("msg", tmp_path / "Foo.txt") is False
    assert [c[2] for c in calls] == ["add", "commit"]


# =============================================================================
# git_revert / git_commit / git_reset_and_revert — timeout handling and
# branch coverage. Consolidated from both loops' test suites (#1603).
# =============================================================================
def test_git_revert_returns_true_on_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    class _R:
        returncode = 0

    monkeypatch.setattr(shared.subprocess, "run", lambda argv, **k: _R())

    assert shared.git_revert(tmp_path / "Foo.txt") is True


def test_git_revert_returns_false_on_nonzero_exit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    class _R:
        returncode = 1

    monkeypatch.setattr(shared.subprocess, "run", lambda argv, **k: _R())

    assert shared.git_revert(tmp_path / "Foo.txt") is False


def test_git_revert_passes_a_timeout_to_subprocess_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    captured: dict = {}

    class _R:
        returncode = 0

    def fake_run(argv, **k):
        captured.update(k)
        return _R()

    monkeypatch.setattr(shared.subprocess, "run", fake_run)

    shared.git_revert(tmp_path / "Foo.txt")

    assert captured["timeout"] == shared.GIT_TIMEOUT_S


def test_git_revert_returns_false_and_logs_not_raises_on_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    def fake_run(argv, **kwargs):
        raise shared.subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(shared.subprocess, "run", fake_run)

    assert shared.git_revert(tmp_path / "Foo.txt") is False  # must not raise

    err = capsys.readouterr().err
    assert str(shared.GIT_TIMEOUT_S) in err
    assert "DEV_TEAM_MUTATION_GIT_TIMEOUT_S" in err
    assert "git checkout" in err


def test_git_commit_passes_a_timeout_to_add_and_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls: list = []

    class _R:
        returncode = 0

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return _R()

    monkeypatch.setattr(shared.subprocess, "run", fake_run)

    result = shared.git_commit("msg", tmp_path / "Foo.txt")

    assert result is True
    assert calls[0][1]["timeout"] == shared.GIT_TIMEOUT_S
    assert calls[1][1]["timeout"] == shared.GIT_TIMEOUT_S


def test_git_commit_add_leg_timeout_returns_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    def fake_run(argv, **kwargs):
        raise shared.subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(shared.subprocess, "run", fake_run)

    assert shared.git_commit("msg", tmp_path / "Foo.txt") is False
    err = capsys.readouterr().err
    assert str(shared.GIT_TIMEOUT_S) in err
    assert "DEV_TEAM_MUTATION_GIT_TIMEOUT_S" in err
    assert "git add" in err


def test_git_commit_commit_leg_timeout_returns_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    """The `git add` leg succeeds; only the `git commit` leg's own
    subprocess.run call times out — a distinct branch from the add-leg
    timeout above, since git_commit short-circuits on add before ever
    reaching commit."""

    calls: list = []

    class _R:
        returncode = 0

    def fake_run(argv, **kwargs):
        calls.append(argv)
        if len(calls) == 1:
            return _R()
        raise shared.subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(shared.subprocess, "run", fake_run)

    assert shared.git_commit("msg", tmp_path / "Foo.txt") is False
    assert calls[0][:3] == ["git", "--literal-pathspecs", "add"]
    err = capsys.readouterr().err
    assert str(shared.GIT_TIMEOUT_S) in err
    assert "DEV_TEAM_MUTATION_GIT_TIMEOUT_S" in err
    assert "git commit" in err


def test_git_commit_proceeds_to_commit_after_a_non_timeout_add_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Pins the documented behavior: git_commit only inspects git add's
    timeout, not its returncode, so a non-timeout git add failure (e.g. bad
    pathspec) still falls through to attempting the commit."""

    calls: list = []

    class _R:
        def __init__(self, returncode):
            self.returncode = returncode

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return _R(returncode=1) if len(calls) == 1 else _R(returncode=0)

    monkeypatch.setattr(shared.subprocess, "run", fake_run)

    result = shared.git_commit("msg", tmp_path / "Foo.txt")

    assert result is True
    assert len(calls) == 2
    assert calls[1][:3] == ["git", "--literal-pathspecs", "commit"]


def test_git_reset_and_revert_returns_false_when_reset_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls: list = []

    class _R:
        def __init__(self, returncode):
            self.returncode = returncode

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return _R(1)  # reset fails

    monkeypatch.setattr(shared.subprocess, "run", fake_run)

    assert shared.git_reset_and_revert(tmp_path / "Foo.txt") is False
    # Only the reset call happens — checkout (git_revert) is never reached.
    assert len(calls) == 1
    assert calls[0][:3] == ["git", "--literal-pathspecs", "reset"]


def test_git_reset_and_revert_returns_false_when_reset_times_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    def fake_run(argv, **kwargs):
        raise shared.subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(shared.subprocess, "run", fake_run)

    assert shared.git_reset_and_revert(tmp_path / "Foo.txt") is False


def test_git_reset_and_revert_returns_false_when_checkout_fails_after_reset_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls: list = []

    class _R:
        def __init__(self, returncode):
            self.returncode = returncode

    def fake_run(argv, **kwargs):
        calls.append(argv)
        if argv[2] == "reset":
            return _R(0)  # reset succeeds
        return _R(1)  # checkout (git_revert) fails

    monkeypatch.setattr(shared.subprocess, "run", fake_run)

    assert shared.git_reset_and_revert(tmp_path / "Foo.txt") is False
    assert [c[2] for c in calls] == ["reset", "checkout"]
