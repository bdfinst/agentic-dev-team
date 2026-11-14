"""Where the repo keeps copies of the answer key a sandboxed trial must not read.

The expected entries live in `evals/expected` in the main checkout and in every
linked worktree, and every committed version of them lives in the git object
store. A sandboxed trial's `denyRead` list names all of these, alongside the
run's own frozen copy (see `snapshot`).
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

from . import paths

EXPECTED_RELATIVE = Path("evals") / "expected"
WORKTREE_PREFIX = "worktree "

# Runs git with these arguments in the repo and returns stdout; raises on failure.
GitRunner = Callable[[Sequence[str]], str]


def _run_git(args: Sequence[str]) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=paths.REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def worktree_roots(porcelain: str) -> list[Path]:
    """The checkout roots `git worktree list --porcelain` names, the main one first."""
    return [
        Path(line[len(WORKTREE_PREFIX) :])
        for line in porcelain.splitlines()
        if line.startswith(WORKTREE_PREFIX)
    ]


def repo_answer_key_paths(
    repo_root: Path = paths.REPO_ROOT, run_git: GitRunner = _run_git
) -> tuple[Path, ...]:
    """The repo's git directory, and each checkout's `.git` entry and `evals/expected`.

    `repo_root`'s own entries are always included. When git cannot be run or
    the repo is not a git checkout, only those are returned.
    """
    roots = [repo_root]
    found: list[Path] = []
    try:
        common_dir = Path(run_git(["rev-parse", "--git-common-dir"]).strip())
        found.append(common_dir if common_dir.is_absolute() else repo_root / common_dir)
        roots.extend(worktree_roots(run_git(["worktree", "list", "--porcelain"])))
    except (OSError, subprocess.CalledProcessError):
        pass
    for root in roots:
        found.extend((root / ".git", root / EXPECTED_RELATIVE))
    unique: dict[str, Path] = {}
    for path in found:
        resolved = path.resolve()
        unique.setdefault(str(resolved), resolved)
    return tuple(unique.values())
