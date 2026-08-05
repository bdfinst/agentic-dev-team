"""Unit tests for tests/lib/concurrency.py (#1889)."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parent
_REPO_TESTS = Path(__file__).resolve().parents[4] / "tests" / "repo"
for _p in (_LIB, _REPO_TESTS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import concurrency  # type: ignore[import-not-found]
import test_hermetic_adoption  # type: ignore[import-not-found]


def test_git_mutating_verbs_matches_hermetic_adoption_gate() -> None:
    """Kept in lockstep per concurrency.py's own comment — this test is what
    actually enforces that claim rather than leaving it to a comment."""
    assert concurrency._GIT_MUTATING_VERBS == test_hermetic_adoption._PY_MUTATING_VERBS


def _cmd(*args: str) -> list:
    return [sys.executable, "-c", *args]


def test_run_concurrently_preserves_input_order() -> None:
    cmds = [
        (_cmd(f"print({i})"), "", None)
        for i in range(5)
    ]
    results = concurrency.run_concurrently(cmds)
    outputs = [out.strip() for _rc, out, _err in results]
    assert outputs == ["0", "1", "2", "3", "4"]


def test_run_concurrently_captures_returncode_per_command() -> None:
    cmds = [
        (_cmd("import sys; sys.exit(0)"), "", None),
        (_cmd("import sys; sys.exit(7)"), "", None),
    ]
    results = concurrency.run_concurrently(cmds)
    assert [rc for rc, _out, _err in results] == [0, 7]


def test_run_concurrently_attributes_stdout_and_stderr_to_the_right_command() -> None:
    cmds = [
        (_cmd("print('out-a'); import sys; print('err-a', file=sys.stderr)"), "", None),
        (_cmd("print('out-b'); import sys; print('err-b', file=sys.stderr)"), "", None),
    ]
    results = concurrency.run_concurrently(cmds)
    assert results[0][1].strip() == "out-a"
    assert results[0][2].strip() == "err-a"
    assert results[1][1].strip() == "out-b"
    assert results[1][2].strip() == "err-b"


def test_run_concurrently_times_out_instead_of_hanging() -> None:
    cmds = [(_cmd("import time; time.sleep(30)"), "", None)]
    results = concurrency.run_concurrently(cmds, timeout=0.5)
    rc, _out, err = results[0]
    assert rc is None
    assert "TIMEOUT" in err


def test_run_concurrently_rejects_mutating_git_argv_without_env() -> None:
    cmds = [(["git", "commit", "-m", "x"], "", None)]
    try:
        concurrency.run_concurrently(cmds)
    except ValueError as exc:
        assert "env=None" in str(exc)
    else:
        raise AssertionError("expected a ValueError for unhermetic mutating git argv")


@pytest.mark.skipif(shutil.which("git") is None, reason="requires git on PATH")
def test_run_concurrently_allows_mutating_git_argv_with_explicit_env() -> None:
    # "commit --help" matches the mutating-verb guard (argv[1] == "commit")
    # without actually mutating anything, so this genuinely exercises the
    # env-is-not-None allow path rather than short-circuiting on the verb
    # check the way a non-mutating "--version" would.
    cmds = [(["git", "commit", "--help"], "", {"PATH": os.environ.get("PATH", "")})]
    results = concurrency.run_concurrently(cmds)
    assert results[0][0] == 0


def test_run_concurrently_allows_non_mutating_git_argv_without_env() -> None:
    cmds = [(["git", "--version"], "", None)]
    results = concurrency.run_concurrently(cmds)
    assert results[0][0] == 0


def test_assert_concurrent_appends_rejects_duplicate_markers(tmp_path: Path) -> None:
    log = tmp_path / "log.jsonl"
    cmds = [(_cmd("pass"), None), (_cmd("pass"), None)]
    try:
        concurrency.assert_concurrent_appends_produce_one_line_per_marker(
            cmds, log, ["same", "same"]
        )
    except AssertionError as exc:
        assert "unique" in str(exc)
    else:
        raise AssertionError("expected an AssertionError for duplicate markers")
