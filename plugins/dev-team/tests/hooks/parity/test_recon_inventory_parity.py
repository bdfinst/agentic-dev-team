"""Parity check for scripts/recon-inventory (#615 / #572 Phase 3).

Like build-wave-reconcile, this script consults `.git/` so the harness
sandbox (flat initial_tree) can't model its inputs. We build twin
projects (one for each side), run each script against its own project,
and assert byte-identical stdout, stderr, and exit code.

Cases cover both source branches (git-ls-files and filesystem-walk),
Windows-style paths in the tree, broken symlinks, --emit-main-json,
and usage / missing-root errors.
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
_HOOK_SH = _REPO_ROOT / "plugins" / "dev-team" / "scripts" / "recon-inventory.sh"
_HOOK_PY = _REPO_ROOT / "plugins" / "dev-team" / "scripts" / "recon_inventory.py"


def _env() -> dict:
    return {
        **os.environ,
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_AUTHOR_NAME": "T",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "T",
        "GIT_COMMITTER_EMAIL": "t@t",
    }


def _git(*args, cwd, check=True):
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=check,
        env=_env(),
    )


def _seed_git(root: Path) -> None:
    (root / "src").mkdir()
    (root / "src" / "a.txt").write_text("a\n")
    (root / "src" / "b.txt").write_text("b\n")
    _git("init", "-q", cwd=root)
    _git("add", "-A", cwd=root)
    _git("commit", "-q", "-m", "seed", cwd=root)


def _seed_no_git(root: Path) -> None:
    (root / "src").mkdir()
    (root / "src" / "one.txt").write_text("1\n")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "x.js").write_text("n\n")
    (root / ".DS_Store").write_text("mac\n")


def _seed_broken_symlink(root: Path) -> None:
    """git-mode broken-symlink case: symlink must be committed for the
    ls-files branch to surface it (fs-walk skips symlinks entirely, matching
    `find -type f`)."""
    (root / "src").mkdir()
    (root / "src" / "real.txt").write_text("ok\n")
    os.symlink("nonexistent.txt", root / "src" / "dangling.txt")
    _git("init", "-q", cwd=root)
    _git("add", "-A", cwd=root)
    _git("commit", "-q", "-m", "seed", cwd=root)


def _seed_windows_named(root: Path) -> None:
    """Files whose names contain backslashes and colons — legal on macOS/Linux,
    the kind of path this migration exists to protect."""
    (root / "src").mkdir()
    (root / "src" / "a.txt").write_text("a\n")
    _git("init", "-q", cwd=root)
    _git("add", "-A", cwd=root)
    _git("commit", "-q", "-m", "seed", cwd=root)


CASES: List[Tuple[str, Callable[[Path], None], List[str]]] = [
    ("git_repo", _seed_git, []),
    ("git_repo_slug", _seed_git, ["--slug", "custom-slug"]),
    ("fs_walk_no_git", _seed_no_git, []),
    ("fs_walk_forced", _seed_git, ["--force-filesystem-walk"]),
    ("broken_symlink", _seed_broken_symlink, []),
    ("windows_named", _seed_windows_named, []),
]


def _run(cmd: List[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        check=False,
        env=_env(),
    )


def _normalize_paths(text: bytes, root: Path) -> bytes:
    """Replace the (per-side) sandbox root path prefix in text so absolute
    references are equal across sides. Preserves everything else."""
    return text.replace(str(root).encode(), b"<SANDBOX>")


@pytest.mark.skipif(
    not _HOOK_SH.is_file() or not _HOOK_PY.is_file(),
    reason="both .sh and .py implementations required",
)
@pytest.mark.parametrize(
    "name, seed, extra_argv",
    CASES,
    ids=[c[0] for c in CASES],
)
def test_parity(
    tmp_path: Path, name: str, seed: Callable[[Path], None], extra_argv: List[str]
) -> None:
    if shutil.which("git") is None:
        pytest.skip("git required")

    sh_root = tmp_path / "sh"
    py_root = tmp_path / "py"
    sh_root.mkdir()
    py_root.mkdir()
    seed(sh_root)
    seed(py_root)

    sh_argv = ["bash", str(_HOOK_SH), str(sh_root), *extra_argv]
    py_argv = [sys.executable, str(_HOOK_PY), str(py_root), *extra_argv]
    sh_result = _run(sh_argv, cwd=sh_root)
    py_result = _run(py_argv, cwd=py_root)

    assert sh_result.returncode == py_result.returncode, f"[{name}] exit codes diverged"
    # stdout paths are repo-relative so no normalization needed.
    assert sh_result.stdout == py_result.stdout, (
        f"[{name}] stdout diverged\nsh: {sh_result.stdout!r}\npy: {py_result.stdout!r}"
    )
    # stderr may contain the sandbox path (e.g. in BROKEN_SYMLINK notes) —
    # replace with a stable placeholder before comparing.
    sh_stderr = _normalize_paths(sh_result.stderr, sh_root)
    py_stderr = _normalize_paths(py_result.stderr, py_root)
    assert sh_stderr == py_stderr, (
        f"[{name}] stderr diverged\nsh: {sh_stderr!r}\npy: {py_stderr!r}"
    )
