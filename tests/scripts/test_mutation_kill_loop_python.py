"""Pytest tests for mutation_kill_loop_python.py's mutmut invocation
mechanics — the scoped ``mutmut run``/``junitxml`` subprocess wiring and the
``.mutmut-cache`` lock (#1357, split further in #1604 mirroring the C#
loop's own #1564 split of ``test_mutation_kill_loop.py``).

Every mutmut / git subprocess is mocked — no real mutmut run happens here
(that's covered by the manual, real-tool dogfooding recorded in
#1354/#1357's issue history). Insertion mechanics live in
``test_mutation_kill_insert_python.py`` (#1583) — the C# loop's own test file
follows the same split (insertion tests live only in
``test_mutation_kill_insert.py``, not duplicated here).

Split further (#1604): ``run_for_file`` orchestration moved to
``test_mutation_kill_loop_python_orchestration.py``, ``python_compiles``/
``run_scoped_pytest`` verify wiring plus the git-helper identity check moved
to ``test_mutation_kill_loop_python_verify.py``, and headless-generation
glue plus CLI dispatch moved to ``test_mutation_kill_loop_python_cli.py`` —
this file now covers only the mutmut subprocess mechanics above and
``extract_survivors``.
"""

from __future__ import annotations

from pathlib import Path

import mutation_kill_loop_python as loop
import pytest
from _mutation_kill_loop_python_test_helpers import _junit, _killed, _survived
from _mutation_test_helpers import FORBIDDEN_LITERALS, SCRIPTS_DIR


# =============================================================================
# run_scoped_mutmut — always reverts source_file (and test_file, when given)
# even when the mutmut subprocess itself crashes (#1357/#1359)
# =============================================================================
def test_run_scoped_mutmut_reverts_source_file_even_when_mutmut_crashes(
    tmp_path: Path, monkeypatch
):
    """mutmut mutates the real source file on disk per-mutant and restores it
    when done — but a mutmut-internal crash (real, reproducible: mutmut
    2.5.1's own cache layer, confirmed while dogfooding this exact function
    against hooks/mutation_adapters/mutmut.py, #1357) skips that restore and
    leaves mutated content on disk. run_scoped_mutmut must always revert the
    source file, even when the mutmut subprocess itself raises."""
    monkeypatch.setattr(loop, "_mutmut_argv", lambda: ["mutmut"])

    def boom(*_a, **_k):
        raise RuntimeError("simulated mutmut internal crash")

    monkeypatch.setattr(loop.subprocess, "run", boom)

    reverted = []
    monkeypatch.setattr(loop, "git_revert", lambda path, **k: reverted.append(path))

    with pytest.raises(RuntimeError):
        loop.run_scoped_mutmut("src/a.py", test_command="pytest", cwd=tmp_path)

    assert reverted == [Path("src/a.py")]


def test_run_scoped_mutmut_reverts_source_file_on_the_success_path_too(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(loop, "_mutmut_argv", lambda: ["mutmut"])

    class _FakeCompleted:
        stdout = "<testsuites></testsuites>"

    monkeypatch.setattr(loop.subprocess, "run", lambda *a, **k: _FakeCompleted())

    reverted = []
    monkeypatch.setattr(loop, "git_revert", lambda path, **k: reverted.append(path))

    loop.run_scoped_mutmut("src/a.py", test_command="pytest", cwd=tmp_path)

    assert reverted == [Path("src/a.py")]


def test_run_scoped_mutmut_reverts_test_file_too_when_mutmut_crashes(
    tmp_path: Path, monkeypatch
):
    """mutmut 2.5.1 has also been observed to corrupt the *runner's test
    file* (truncate it to empty via a crashed .bak-restore, #1359) — not
    just the source file. run_scoped_mutmut must revert both when a
    test_file is supplied, even when the mutmut subprocess itself raises."""
    monkeypatch.setattr(loop, "_mutmut_argv", lambda: ["mutmut"])

    def boom(*_a, **_k):
        raise RuntimeError("simulated mutmut internal crash")

    monkeypatch.setattr(loop.subprocess, "run", boom)

    reverted = []
    monkeypatch.setattr(loop, "git_revert", lambda path, **k: reverted.append(path))

    with pytest.raises(RuntimeError):
        loop.run_scoped_mutmut(
            "src/a.py",
            test_command="pytest",
            test_file=Path("tests/test_a.py"),
            cwd=tmp_path,
        )

    assert reverted == [Path("src/a.py"), Path("tests/test_a.py")]


def test_run_scoped_mutmut_reverts_test_file_on_the_success_path_too(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(loop, "_mutmut_argv", lambda: ["mutmut"])

    class _FakeCompleted:
        stdout = "<testsuites></testsuites>"

    monkeypatch.setattr(loop.subprocess, "run", lambda *a, **k: _FakeCompleted())

    reverted = []
    monkeypatch.setattr(loop, "git_revert", lambda path, **k: reverted.append(path))

    loop.run_scoped_mutmut(
        "src/a.py",
        test_command="pytest",
        test_file=Path("tests/test_a.py"),
        cwd=tmp_path,
    )

    assert reverted == [Path("src/a.py"), Path("tests/test_a.py")]


def test_run_scoped_mutmut_does_not_revert_test_file_when_not_supplied(
    tmp_path: Path, monkeypatch
):
    """Backward compatibility: callers that don't pass test_file (none did
    before #1359) must see identical behavior to before this change."""
    monkeypatch.setattr(loop, "_mutmut_argv", lambda: ["mutmut"])

    class _FakeCompleted:
        stdout = "<testsuites></testsuites>"

    monkeypatch.setattr(loop.subprocess, "run", lambda *a, **k: _FakeCompleted())

    reverted = []
    monkeypatch.setattr(loop, "git_revert", lambda path, **k: reverted.append(path))

    loop.run_scoped_mutmut("src/a.py", test_command="pytest", cwd=tmp_path)

    assert reverted == [Path("src/a.py")]


# =============================================================================
# Scenario: the .mutmut-cache delete/run/revert sequence is lock-guarded so
# two concurrent scoped runs against the same repo can't corrupt each
# other's cache state (#1584)
# =============================================================================
def test_run_scoped_mutmut_releases_the_lock_after_a_successful_run(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(loop, "_mutmut_argv", lambda: ["mutmut"])

    class _FakeCompleted:
        stdout = "<testsuites></testsuites>"

    monkeypatch.setattr(loop.subprocess, "run", lambda *a, **k: _FakeCompleted())
    monkeypatch.setattr(loop, "git_revert", lambda path, **k: None)

    loop.run_scoped_mutmut("src/a.py", test_command="pytest", cwd=tmp_path)

    assert not (tmp_path / ".mutmut-cache.lock").exists()


def test_run_scoped_mutmut_releases_the_lock_even_when_mutmut_crashes(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(loop, "_mutmut_argv", lambda: ["mutmut"])

    def boom(*_a, **_k):
        raise RuntimeError("simulated mutmut internal crash")

    monkeypatch.setattr(loop.subprocess, "run", boom)
    monkeypatch.setattr(loop, "git_revert", lambda path, **k: None)

    with pytest.raises(RuntimeError):
        loop.run_scoped_mutmut("src/a.py", test_command="pytest", cwd=tmp_path)

    assert not (tmp_path / ".mutmut-cache.lock").exists()


def test_acquire_mutmut_cache_lock_times_out_when_already_held(tmp_path: Path):
    held = loop._acquire_mutmut_cache_lock(tmp_path)
    try:
        with pytest.raises(RuntimeError, match="timed out"):
            loop._acquire_mutmut_cache_lock(tmp_path, timeout=0.3)
    finally:
        loop._release_mutmut_cache_lock(held)


def test_acquire_mutmut_cache_lock_succeeds_once_released(tmp_path: Path):
    lock_dir = loop._acquire_mutmut_cache_lock(tmp_path)
    assert lock_dir.exists()
    loop._release_mutmut_cache_lock(lock_dir)
    assert not lock_dir.exists()

    # A second acquire after release must succeed immediately, not raise.
    second = loop._acquire_mutmut_cache_lock(tmp_path, timeout=1)
    loop._release_mutmut_cache_lock(second)


# =============================================================================
# Scenario: the two `mutmut` subprocesses run_scoped_mutmut shells out to
# (the scoped run itself, and the junitxml extraction) are bounded by a
# timeout, not left to hang forever — previously unbounded (#1605), unlike
# the C# loop's DOTNET_BUILD_TIMEOUT_S/DOTNET_TEST_TIMEOUT_S equivalents.
# =============================================================================
def test_run_scoped_mutmut_passes_a_timeout_to_the_mutmut_run_call(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(loop, "_mutmut_argv", lambda: ["mutmut"])
    calls: list = []

    class _FakeCompleted:
        stdout = "<testsuites></testsuites>"

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return _FakeCompleted()

    monkeypatch.setattr(loop.subprocess, "run", fake_run)
    monkeypatch.setattr(loop, "git_revert", lambda *a, **k: None)

    loop.run_scoped_mutmut("src/a.py", test_command="pytest", cwd=tmp_path)

    run_call = next(c for c in calls if c[0][1:2] == ["run"])
    assert run_call[1]["timeout"] == loop._MUTMUT_RUN_TIMEOUT_S
    junitxml_call = next(c for c in calls if c[0][1:2] == ["junitxml"])
    assert junitxml_call[1]["timeout"] == loop._MUTMUT_JUNITXML_TIMEOUT_S


def test_run_scoped_mutmut_run_timeout_raises_a_named_error(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(loop, "_mutmut_argv", lambda: ["mutmut"])

    def fake_run(argv, **kwargs):
        raise loop.subprocess.TimeoutExpired(argv, kwargs.get("timeout"))

    monkeypatch.setattr(loop.subprocess, "run", fake_run)
    monkeypatch.setattr(loop, "git_revert", lambda *a, **k: None)

    with pytest.raises(RuntimeError, match="mutmut run timed out") as exc_info:
        loop.run_scoped_mutmut("src/a.py", test_command="pytest", cwd=tmp_path)

    assert "DEV_TEAM_MUTATION_MUTMUT_TIMEOUT_S" in str(exc_info.value)


def test_run_scoped_mutmut_junitxml_timeout_raises_a_named_error(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(loop, "_mutmut_argv", lambda: ["mutmut"])

    class _FakeCompleted:
        stdout = "<testsuites></testsuites>"

    def fake_run(argv, **kwargs):
        if argv[1:2] == ["run"]:
            return _FakeCompleted()
        raise loop.subprocess.TimeoutExpired(argv, kwargs.get("timeout"))

    monkeypatch.setattr(loop.subprocess, "run", fake_run)
    monkeypatch.setattr(loop, "git_revert", lambda *a, **k: None)

    with pytest.raises(RuntimeError, match="junitxml extraction timed out") as exc_info:
        loop.run_scoped_mutmut("src/a.py", test_command="pytest", cwd=tmp_path)

    assert "DEV_TEAM_MUTATION_MUTMUT_JUNITXML_TIMEOUT_S" in str(exc_info.value)


def test_run_scoped_mutmut_still_reverts_on_a_timeout(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(loop, "_mutmut_argv", lambda: ["mutmut"])

    def fake_run(argv, **kwargs):
        raise loop.subprocess.TimeoutExpired(argv, kwargs.get("timeout"))

    monkeypatch.setattr(loop.subprocess, "run", fake_run)
    reverted = []
    monkeypatch.setattr(loop, "git_revert", lambda path, **k: reverted.append(path))

    with pytest.raises(RuntimeError):
        loop.run_scoped_mutmut("src/a.py", test_command="pytest", cwd=tmp_path)

    assert reverted == [Path("src/a.py")]


# =============================================================================
# extract_survivors — delegates to mutation_report's junitxml support
# =============================================================================
def test_extract_survivors_filters_to_target_file():
    xml = _junit(
        _survived("Mutant #1", "src/a.py", 5),
        _survived("Mutant #2", "src/b.py", 9),
        _killed("Mutant #3", "src/a.py", 1),
        failures=2,
    )
    survivors = loop.extract_survivors(xml, "src/a.py")

    assert len(survivors) == 1
    assert survivors[0]["location"]["start"]["line"] == 5
    assert survivors[0]["mutatorName"] == "mutmut"


# =============================================================================
# Scenario: _release_mutmut_cache_lock swallows a release-time OSError rather
# than masking whatever exception the run itself was raising (#1584 review).
# =============================================================================
def test_release_mutmut_cache_lock_swallows_a_missing_directory(tmp_path: Path):
    lock_dir = tmp_path / ".mutmut-cache.lock"
    lock_dir.mkdir()
    lock_dir.rmdir()  # already gone — simulates a race/double-release

    loop._release_mutmut_cache_lock(lock_dir)  # must not raise


# =============================================================================
# Scenario: the mutmut-cache lock timeout is overridable via env var, not a
# bare magic number (#1584 review, item 9) — mirrors mutation_kill_loop.py's
# _timeout_from_env pattern.
# =============================================================================
def test_mutmut_cache_lock_timeout_is_overridable_via_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DEV_TEAM_MUTATION_MUTMUT_LOCK_TIMEOUT_S", "77")
    import importlib

    reloaded = importlib.reload(loop)
    try:
        assert reloaded._MUTMUT_CACHE_LOCK_TIMEOUT_S == 77
    finally:
        monkeypatch.delenv("DEV_TEAM_MUTATION_MUTMUT_LOCK_TIMEOUT_S", raising=False)
        importlib.reload(loop)


# =============================================================================
# No repo-specific literal leaked into the module — the cross-module sweep
# (checking every file in this split) lives in
# test_mutation_kill_loop_python_cli.py.
# =============================================================================
def test_module_source_carries_no_repo_specific_literal():
    source = (SCRIPTS_DIR / "mutation_kill_loop_python.py").read_text(encoding="utf-8")
    present = [literal for literal in FORBIDDEN_LITERALS if literal in source]
    assert present == [], f"repo-specific literals leaked into module: {present}"
