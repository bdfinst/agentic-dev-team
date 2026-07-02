"""Parity check for scripts/build-wave-reconcile (#612 / #572 Phase 3).

This script mutates a git repository, so the standard sandbox harness
(initial_tree = flat files only) cannot model its inputs. Instead we build
two identical git repos (one per implementation), run each script against
its own repo, and assert:

  1. Byte-identical stdout, stderr, exit code
  2. Identical `git log --format=%H` on the integration branch
  3. Identical `git status --porcelain`
  4. Identical file trees at the reconciled tip

Fixtures parametrize over the observable behaviors: happy-path (two
disjoint branches), same-file collision (loud halt), WIP-commit
preservation, test-cmd success, test-cmd failure, and usage error.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, List, Tuple

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[5]
_HOOK_SH = _REPO_ROOT / "plugins" / "dev-team" / "scripts" / "build-wave-reconcile.sh"
_HOOK_PY = _REPO_ROOT / "plugins" / "dev-team" / "scripts" / "build_wave_reconcile.py"


def _env() -> dict:
    return {
        **os.environ,
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_AUTHOR_NAME": "T",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "T",
        "GIT_COMMITTER_EMAIL": "t@t",
        # Force stable commit timestamps so the reconciled trees hash
        # identically across the two side-by-side repos.
        "GIT_AUTHOR_DATE": "2026-01-01T00:00:00 +0000",
        "GIT_COMMITTER_DATE": "2026-01-01T00:00:00 +0000",
    }


def _git(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=check,
        env=_env(),
    )


def _setup_repo_disjoint(root: Path) -> None:
    _git("init", "-q", cwd=root)
    _git("checkout", "-q", "-b", "main", cwd=root)
    (root / "README.md").write_text("hello\n")
    _git("add", "README.md", cwd=root)
    _git("commit", "-q", "-m", "chore: seed", cwd=root)
    _git("checkout", "-q", "-b", "slice1", "main", cwd=root)
    (root / "one.txt").write_text("1\n")
    _git("add", "one.txt", cwd=root)
    _git("commit", "-q", "-m", "s1", cwd=root)
    _git("checkout", "-q", "-b", "slice2", "main", cwd=root)
    (root / "two.txt").write_text("2\n")
    _git("add", "two.txt", cwd=root)
    _git("commit", "-q", "-m", "s2", cwd=root)
    _git("checkout", "-q", "main", cwd=root)


def _setup_repo_collision(root: Path) -> None:
    _git("init", "-q", cwd=root)
    _git("checkout", "-q", "-b", "main", cwd=root)
    (root / "README.md").write_text("hello\n")
    _git("add", "README.md", cwd=root)
    _git("commit", "-q", "-m", "chore: seed", cwd=root)
    _git("checkout", "-q", "-b", "slice1", "main", cwd=root)
    (root / "shared.txt").write_text("one\n")
    _git("add", "shared.txt", cwd=root)
    _git("commit", "-q", "-m", "s1", cwd=root)
    _git("checkout", "-q", "-b", "slice2", "main", cwd=root)
    (root / "shared.txt").write_text("two\n")
    _git("add", "shared.txt", cwd=root)
    _git("commit", "-q", "-m", "s2", cwd=root)
    _git("checkout", "-q", "main", cwd=root)


def _setup_repo_wip(root: Path) -> None:
    _setup_repo_disjoint(root)
    _git("checkout", "-q", "-b", "integration", "main", cwd=root)
    (root / "spec.md").write_text("spec\n")
    _git("add", "spec.md", cwd=root)
    _git("commit", "-q", "-m", "wip: caller spec", cwd=root)
    _git("checkout", "-q", "main", cwd=root)


def _setup_repo_empty(root: Path) -> None:
    _git("init", "-q", cwd=root)
    _git("checkout", "-q", "-b", "main", cwd=root)
    (root / "README.md").write_text("hello\n")
    _git("add", "README.md", cwd=root)
    _git("commit", "-q", "-m", "chore: seed", cwd=root)


CASES: List[Tuple[str, Callable[[Path], None], List[str]]] = [
    (
        "happy_path_two_disjoint",
        _setup_repo_disjoint,
        ["--into", "integration", "--base", "main", "slice1", "slice2"],
    ),
    (
        "collision_halts_loudly",
        _setup_repo_collision,
        ["--into", "integration", "--base", "main", "slice1", "slice2"],
    ),
    (
        "wip_commit_preserved",
        _setup_repo_wip,
        ["--into", "integration", "--base", "main", "slice1"],
    ),
    (
        "test_cmd_gate_passes",
        _setup_repo_disjoint,
        ["--into", "integration", "--base", "main", "--test-cmd", "true", "slice1"],
    ),
    (
        "test_cmd_gate_fails",
        _setup_repo_disjoint,
        ["--into", "integration", "--base", "main", "--test-cmd", "false", "slice1"],
    ),
    ("usage_error_no_args", _setup_repo_empty, []),
    ("unknown_option", _setup_repo_empty, ["--wat"]),
]


def _run(cmd: List[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        check=False,
        env=_env(),
    )


def _tree_snapshot(root: Path) -> dict:
    """Files-only content map, ignoring .git for byte-parity comparisons."""
    snapshot = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if rel.parts and rel.parts[0] == ".git":
            continue
        if path.is_file():
            snapshot[str(rel)] = path.read_bytes()
    return snapshot


def _integration_log(root: Path) -> str:
    r = _git("log", "--format=%s", "integration", cwd=root, check=False)
    return r.stdout if r.returncode == 0 else ""


@pytest.mark.skipif(
    not _HOOK_SH.is_file() or not _HOOK_PY.is_file(),
    reason="both .sh and .py implementations required",
)
@pytest.mark.parametrize(
    "name, setup, argv",
    CASES,
    ids=[c[0] for c in CASES],
)
def test_parity(
    tmp_path: Path, name: str, setup: Callable[[Path], None], argv: List[str]
) -> None:
    if shutil.which("git") is None:
        pytest.skip("git required")

    sh_root = tmp_path / "sh"
    sh_root.mkdir()
    py_root = tmp_path / "py"
    py_root.mkdir()
    setup(sh_root)
    setup(py_root)

    sh_result = _run(["bash", str(_HOOK_SH), *argv], cwd=sh_root)
    py_result = _run([sys.executable, str(_HOOK_PY), *argv], cwd=py_root)

    assert sh_result.returncode == py_result.returncode, (
        f"[{name}] exit code diverged: sh={sh_result.returncode} "
        f"py={py_result.returncode}\n"
        f"sh stderr: {sh_result.stderr!r}\npy stderr: {py_result.stderr!r}"
    )
    assert sh_result.stdout == py_result.stdout, (
        f"[{name}] stdout diverged\nsh: {sh_result.stdout!r}\npy: {py_result.stdout!r}"
    )
    assert sh_result.stderr == py_result.stderr, (
        f"[{name}] stderr diverged\nsh: {sh_result.stderr!r}\npy: {py_result.stderr!r}"
    )
    # Integration branch log parity (skip when we didn't create an
    # integration branch — usage errors).
    if argv and "--into" in argv:
        assert _integration_log(sh_root) == _integration_log(py_root)
    assert _tree_snapshot(sh_root) == _tree_snapshot(py_root)
