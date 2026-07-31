"""Pytest tests for mutation_kill_loop_python.py's verify/commit subprocess
wiring — ``python_compiles``/``run_scoped_pytest`` (#1604 split of
``test_mutation_kill_loop_python.py``, mirroring the C# loop's own #1564
split into ``test_mutation_kill_loop_verify.py``). Every subprocess is
mocked; no real Python tooling runs.

``git_revert``/``git_commit``/``git_reset_and_revert`` are re-exported
bindings onto ``mutation_kill_shared.py``'s implementation (#1583); their
full behavioral suite (timeout handling, argv shape, add/commit/reset branch
coverage) lives in ``test_mutation_kill_shared.py`` as the single source of
truth (#1603) — this file keeps only the identity check below, confirming
the re-export stays wired to the shared implementation rather than drifting
into a local copy.

The script's CLI dispatch, headless-generation glue, and the cross-module
no-repo-specific-literal sweep live in
``test_mutation_kill_loop_python_cli.py`` — a separate file so this one
stays scoped to the verify/commit subprocess primitives alone.
"""

from __future__ import annotations

from pathlib import Path

import _mutation_kill_loop_python_test_helpers  # noqa: F401 (sys.path side effect)

import mutation_kill_loop_python as loop  # noqa: E402
import mutation_kill_shared as shared  # noqa: E402


# =============================================================================
# Scenario: python_compiles / run_scoped_pytest are bounded by a timeout
# (#1605) and guard a dash-leading test_file path against being parsed as a
# CLI flag instead of a positional filename (#1607).
# =============================================================================
def test_python_compiles_passes_a_timeout(tmp_path: Path, monkeypatch):
    captured: dict = {}

    class _R:
        returncode = 0

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured.update(kwargs)
        return _R()

    monkeypatch.setattr(loop.subprocess, "run", fake_run)
    loop.python_compiles(tmp_path / "test_a.py")

    assert captured["timeout"] == loop._PYTHON_COMPILE_TIMEOUT_S


def test_python_compiles_returns_false_on_a_timeout(tmp_path: Path, monkeypatch):
    def fake_run(argv, **kwargs):
        raise loop.subprocess.TimeoutExpired(argv, kwargs.get("timeout"))

    monkeypatch.setattr(loop.subprocess, "run", fake_run)
    assert loop.python_compiles(tmp_path / "test_a.py") is False


def test_run_scoped_pytest_passes_a_timeout(tmp_path: Path, monkeypatch):
    captured: dict = {}

    class _R:
        returncode = 0

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured.update(kwargs)
        return _R()

    monkeypatch.setattr(loop.subprocess, "run", fake_run)
    loop.run_scoped_pytest(tmp_path / "test_a.py")

    assert captured["timeout"] == loop._PYTEST_TIMEOUT_S


def test_run_scoped_pytest_returns_false_on_a_timeout(tmp_path: Path, monkeypatch):
    def fake_run(argv, **kwargs):
        raise loop.subprocess.TimeoutExpired(argv, kwargs.get("timeout"))

    monkeypatch.setattr(loop.subprocess, "run", fake_run)
    assert loop.run_scoped_pytest(tmp_path / "test_a.py") is False


def test_run_scoped_pytest_neutralizes_a_dash_leading_test_file_path(monkeypatch):
    """A test_file whose str() starts with '-' (e.g. a path component named
    '-p') must not reach pytest's argv as a bare token, where it would be
    parsed as an option (-p in particular lets pytest import an arbitrary
    module) rather than a nonexistent filename (#1607)."""
    captured: dict = {}

    class _R:
        returncode = 0

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return _R()

    monkeypatch.setattr(loop.subprocess, "run", fake_run)
    loop.run_scoped_pytest(Path("-p"))

    path_arg = captured["argv"][-1]
    assert not path_arg.startswith("-")
    assert path_arg == "./-p"


def test_python_compiles_neutralizes_a_dash_leading_test_file_path(monkeypatch):
    captured: dict = {}

    class _R:
        returncode = 0

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return _R()

    monkeypatch.setattr(loop.subprocess, "run", fake_run)
    loop.python_compiles(Path("-q"))

    path_arg = captured["argv"][-1]
    assert not path_arg.startswith("-")
    assert path_arg == "./-q"


# =============================================================================
# git_revert / git_commit / git_reset_and_revert — identity check only.
# Full behavioral coverage (timeout handling, argv shape, add/commit/reset
# branch coverage) lives in test_mutation_kill_shared.py as the single
# source of truth (#1603); this confirms the re-export stays wired to that
# shared implementation rather than drifting into a local copy.
# =============================================================================
def test_git_helpers_are_the_shared_implementation():
    assert loop.git_revert is shared.git_revert
    assert loop.git_commit is shared.git_commit
    assert loop.git_reset_and_revert is shared.git_reset_and_revert
