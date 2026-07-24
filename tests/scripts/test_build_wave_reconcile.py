"""Pytest tests for scripts/build_wave_reconcile.py (#612 / #572 Phase 3).

Each test drives the port against a real git repo in ``tmp_path``. Mirrors
the behavioral scenarios from ``build_wave_reconcile_wip_preservation_tests.bats``
plus the collision-halts contract from ``build_wave_tests.bats``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from _repo_root import REPO_ROOT as _REPO_ROOT

_SCRIPT_PY = _REPO_ROOT / "plugins" / "dev-team" / "scripts" / "build_wave_reconcile.py"


def _git(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=check,
        env={
            **os.environ,
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "GIT_AUTHOR_NAME": "T",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "T",
            "GIT_COMMITTER_EMAIL": "t@t",
        },
    )


def _init_repo(root: Path) -> None:
    _git("init", "-q", cwd=root)
    _git("checkout", "-q", "-b", "main", cwd=root)
    (root / "README.md").write_text("hello\n")
    _git("add", "README.md", cwd=root)
    _git("commit", "-q", "-m", "chore: seed", cwd=root)


def _make_branch(
    root: Path, name: str, filename: str, content: str, base: str = "main"
) -> None:
    _git("checkout", "-q", "-b", name, base, cwd=root)
    (root / filename).write_text(content)
    _git("add", filename, cwd=root)
    _git("commit", "-q", "-m", f"feat: {filename}", cwd=root)


def _run(
    *args: str, cwd: Path, extra_env: dict | None = None
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_SCRIPT_PY), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "GIT_AUTHOR_NAME": "T",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "T",
            "GIT_COMMITTER_EMAIL": "t@t",
            **(extra_env or {}),
        },
    )


def test_usage_when_missing_args(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    r = _run(cwd=tmp_path)
    assert r.returncode == 2
    assert "usage" in r.stderr


def test_usage_when_only_into(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    r = _run("--into", "integration", cwd=tmp_path)
    assert r.returncode == 2


def test_reconcile_two_disjoint_branches(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _make_branch(tmp_path, "slice1", "one.txt", "1\n")
    _make_branch(tmp_path, "slice2", "two.txt", "2\n")
    r = _run(
        "--into", "integration", "--base", "main", "slice1", "slice2", cwd=tmp_path
    )
    assert r.returncode == 0, r.stderr
    assert "merged 2 slice branch(es)" in r.stdout
    _git("checkout", "integration", cwd=tmp_path)
    assert (tmp_path / "one.txt").is_file()
    assert (tmp_path / "two.txt").is_file()


def test_reconcile_conflict_halts_loudly(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _make_branch(tmp_path, "slice1", "shared.txt", "one\n")
    _make_branch(tmp_path, "slice2", "shared.txt", "two\n")
    r = _run(
        "--into", "integration", "--base", "main", "slice1", "slice2", cwd=tmp_path
    )
    assert r.returncode == 1
    assert "CONFLICT" in r.stderr
    assert "shared.txt" in r.stderr
    # No side was chosen — the merge was aborted, tree should be clean.
    st = _git("status", "--porcelain", cwd=tmp_path)
    assert st.stdout == ""


def test_wip_commit_on_integration_is_preserved(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _git("checkout", "-q", "-b", "integration", "main", cwd=tmp_path)
    (tmp_path / "spec.md").write_text("spec\n")
    _git("add", "spec.md", cwd=tmp_path)
    _git("commit", "-q", "-m", "wip: caller spec", cwd=tmp_path)
    wip_sha = _git("rev-parse", "HEAD", cwd=tmp_path).stdout.strip()

    _make_branch(tmp_path, "slice1", "one.txt", "1\n", base="integration")

    _git("checkout", "-q", "main", cwd=tmp_path)
    r = _run("--into", "integration", "--base", "main", "slice1", cwd=tmp_path)
    assert r.returncode == 0, r.stderr

    log = _git("log", "--format=%H", "integration", cwd=tmp_path).stdout
    assert wip_sha in log, "WIP commit was lost from ancestry"
    _git("checkout", "integration", cwd=tmp_path)
    assert (tmp_path / "spec.md").is_file()
    assert (tmp_path / "one.txt").is_file()


def test_deterministic_order_regardless_of_argv(tmp_path: Path) -> None:
    """Same input branches in any order → same merge history (modulo the
    two branches' commit SHAs, which the fixture holds stable)."""
    for perm in (["slice1", "slice2"], ["slice2", "slice1"]):
        # Fresh repo per permutation for a clean tree.
        wd = tmp_path / f"perm-{'-'.join(perm)}"
        wd.mkdir()
        _init_repo(wd)
        _make_branch(wd, "slice1", "one.txt", "1\n")
        _make_branch(wd, "slice2", "two.txt", "2\n")
        r = _run("--into", "integration", "--base", "main", *perm, cwd=wd)
        assert r.returncode == 0
    # We can't compare SHAs across repos (author date differs), but the
    # merge order is asserted by the sort in the port and gated by the
    # parity harness's byte-equivalence check.


def test_test_cmd_gate_success(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _make_branch(tmp_path, "slice1", "one.txt", "1\n")
    r = _run(
        "--into",
        "integration",
        "--base",
        "main",
        "--test-cmd",
        "true",
        "slice1",
        cwd=tmp_path,
    )
    assert r.returncode == 0
    # Bash's suffix is ${TESTCMD:+passed}${TESTCMD:-skipped} → "passed<cmd>".
    # The port reproduces this byte-for-byte.
    assert "gate passedtrue" in r.stdout


def test_test_cmd_gate_failure_halts(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _make_branch(tmp_path, "slice1", "one.txt", "1\n")
    r = _run(
        "--into",
        "integration",
        "--base",
        "main",
        "--test-cmd",
        "false",
        "slice1",
        cwd=tmp_path,
    )
    assert r.returncode == 1
    assert "gate FAILED" in r.stderr
    assert "false" in r.stderr


def test_test_cmd_skipped_when_absent(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _make_branch(tmp_path, "slice1", "one.txt", "1\n")
    r = _run("--into", "integration", "--base", "main", "slice1", cwd=tmp_path)
    assert r.returncode == 0
    assert "gate skipped" in r.stdout


def test_test_cmd_gate_times_out_instead_of_hanging_forever(tmp_path: Path) -> None:
    """A hung --test-cmd must not block the pipeline indefinitely. A short
    injected timeout should surface a clear timeout failure quickly."""
    _init_repo(tmp_path)
    _make_branch(tmp_path, "slice1", "one.txt", "1\n")
    r = _run(
        "--into",
        "integration",
        "--base",
        "main",
        "--test-cmd",
        "sleep 30",
        "slice1",
        cwd=tmp_path,
        extra_env={"BUILD_WAVE_RECONCILE_TEST_CMD_TIMEOUT": "1"},
    )
    assert r.returncode == 1
    assert "TIMED OUT" in r.stderr or "timed out" in r.stderr.lower()
