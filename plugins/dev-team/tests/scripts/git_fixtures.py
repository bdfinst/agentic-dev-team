"""Shared git fixtures for the #2275 tests (commit_evidence, feature_record).

A temporary repository must never be redirected into the parent worktree by a
git variable the test runner inherited (a pre-push hook exports several), and
must never read the host's git configuration. Call `isolate_git` from a thin
autouse fixture in the test module; build repositories with `init` / `commit`.

`tests/scripts/test_progress_guardian.py` keeps its own copy of this scrub: the
two test trees do not import each other.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

SCRUBBED_VARS = (
    "GIT_DIR",
    "GIT_COMMON_DIR",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_NAMESPACE",
    "GIT_WORK_TREE",
    "GIT_PREFIX",
    "GIT_REFLOG_ACTION",
)


def isolate_git(monkeypatch, ceilings: list[Path]) -> None:
    """Scrub inherited git variables, ignore host config, and stop git's
    upward repository search at each of `ceilings`."""
    for key in SCRUBBED_VARS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", os.pathsep.join(map(str, ceilings)))


def git(cwd: Path, *args: str) -> str:
    """Run git in `cwd` under the current (isolated) environment; return stdout."""
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env=dict(os.environ),
    )
    return result.stdout.strip()


def init(cwd: Path, branch: str = "main") -> None:
    git(cwd, "init", "-q", f"--initial-branch={branch}")
    git(cwd, "config", "user.email", "test@test.com")
    git(cwd, "config", "user.name", "Test")


def commit(cwd: Path, name: str | None, message: str) -> None:
    """Commit a new file `name` (or an empty commit when `name` is None)."""
    if name is None:
        git(cwd, "commit", "-q", "--allow-empty", "-m", message)
        return
    target = cwd / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("work\n")
    git(cwd, "add", name)
    git(cwd, "commit", "-q", "-m", message)


def remove_loose_object(root: Path, sha: str) -> None:
    """Delete a loose object, to make the git commands that read it fail while
    the ones that do not (for example `git log`) keep working."""
    path = root / ".git" / "objects" / sha[:2] / sha[2:]
    assert path.exists(), "the fault needs a loose object"
    path.parent.chmod(0o755)
    path.chmod(0o644)
    path.unlink()
