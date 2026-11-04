"""Fixtures and recorders for tests/scripts/test_lane.py.

Fixture **N**: a repository with no remote, trunk `main`.
Fixture **R**: a repository with a non-github bare `origin` (built with
`git clone --bare`), remote-tracking trunk `origin/main` equal to local `main`.
The bare origin is advanced without a push: `update-ref` inside the bare
repository, then `git fetch` in the working repository.

Both commit a `.gitignore` containing `.claude/` on trunk before any lane
exists, so gate and ledger files never make a lane dirty.

Named without a leading `test_` so pytest does not collect it. Not a conftest:
a plain importable module, like `_mutation_test_helpers.py`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from _repo_root import REPO_ROOT

_HERMETIC_DIR = REPO_ROOT / "plugins" / "dev-team" / "tests" / "lib"
if str(_HERMETIC_DIR) not in sys.path:
    sys.path.insert(0, str(_HERMETIC_DIR))

from hermetic import hermetic_git_env  # type: ignore[import-not-found]

TRUNK = "main"
GITIGNORE = ".claude/\n"

#: The oracle for "never pushes, never skips hooks". Deliberately written out
#: here instead of imported from lane_core: a test must not trust the code it
#: checks to define what is forbidden. Exact token equality, never substring.
FORBIDDEN_TOKENS = frozenset(
    {
        "push",
        "send-pack",
        "--no-verify",
        "--force",
        "--force-with-lease",
        "-f",
        "--no-gpg-sign",
    }
)
HOOKS_PATH_PREFIX = "core.hookspath="

_IDENTITY = {
    "GIT_AUTHOR_NAME": "lane tester",
    "GIT_AUTHOR_EMAIL": "lane@example.test",
    "GIT_COMMITTER_NAME": "lane tester",
    "GIT_COMMITTER_EMAIL": "lane@example.test",
}


def git_env(home: Path) -> dict[str, str]:
    """Hermetic git environment with a fixed commit identity."""
    return {**hermetic_git_env(home=home), **_IDENTITY}


def git(cwd: Path, *args: str, home: Path | None = None) -> str:
    """Run a fixture git command (hermetic env, must succeed); return stdout."""
    done = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=git_env(home or cwd),
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


def commit_file(repo: Path, name: str, content: str, message: str) -> str:
    """Write `name`, commit it, return the new commit SHA."""
    (repo / name).write_text(content, encoding="utf-8")
    git(repo, "add", "--", name)
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def covers(what: str):
    """Index which test covers which refusal `what`.

    A no-op decorator: `test_lane.py` reads the literal from the source (AST),
    so the coverage check does not depend on selection or execution order.
    """

    def decorate(test):
        return test

    return decorate


@dataclass(frozen=True)
class Repo:
    """A fixture repository. `origin` is the bare repository, or None."""

    path: Path
    origin: Path | None


def build_fixture_n(root: Path) -> Repo:
    """Fixture N: no remote, trunk `main`, `.claude/` ignored."""
    path = root / "repo"
    path.mkdir()
    git(path, "init", "-q", "-b", TRUNK, home=root)
    (path / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
    commit_file(path, "base.txt", "base\n", "base")
    git(path, "add", ".gitignore")
    git(path, "commit", "-q", "-m", "ignore .claude")
    return Repo(path=path, origin=None)


def build_fixture_r(root: Path) -> Repo:
    """Fixture R: fixture N plus a bare non-github `origin` at the same tip."""
    repo = build_fixture_n(root)
    origin = root / "origin.git"
    git(root, "clone", "-q", "--bare", str(repo.path), str(origin), home=root)
    git(repo.path, "remote", "add", "origin", str(origin))
    git(repo.path, "fetch", "-q", "origin")
    return Repo(path=repo.path, origin=origin)


def advance_origin(
    repo: Repo, branch: str = TRUNK, message: str = "origin moved"
) -> str:
    """Move the bare origin's `branch` one commit ahead, then fetch. No push."""
    assert repo.origin is not None
    tip = git(repo.origin, "rev-parse", f"refs/heads/{branch}")
    tree = git(repo.origin, "rev-parse", f"{tip}^{{tree}}")
    new = git(repo.origin, "commit-tree", tree, "-p", tip, "-m", message)
    git(repo.origin, "update-ref", f"refs/heads/{branch}", new)
    git(repo.path, "fetch", "-q", "origin")
    return new


def add_linked_worktree(repo: Repo, branch: str, start: str = TRUNK) -> Path:
    """A linked worktree on a new `branch`, placed beside the primary checkout."""
    path = repo.path.parent / f"{repo.path.name}-lane-{branch.replace('/', '-')}"
    git(repo.path, "worktree", "add", "-q", "-b", branch, str(path), start)
    return path


def parse_blocks(stderr: str) -> list[dict[str, str]]:
    """Split renderer output into `{refused, why, how}` dicts, one per block."""
    blocks: list[dict[str, str]] = []
    for line in stderr.splitlines():
        key, sep, value = line.partition(": ")
        if sep and key == "refused":
            blocks.append({})
        if sep and key in {"refused", "why", "how"}:
            blocks[-1][key] = value
    return blocks


def forbidden_hits(argv: Sequence[str]) -> list[str]:
    """Tokens of one recorded argv that the tool must never pass."""
    return [
        token
        for token in argv
        if token in FORBIDDEN_TOKENS or token.lower().startswith(HOOKS_PATH_PREFIX)
    ]


class ArgvSpy:
    """Records every argv started through `subprocess.run` or `subprocess.Popen`.

    Patched on the `subprocess` module itself, so a call made inside an
    imported library module is recorded too. `run` is recorded once: while a
    `run` is in flight its inner `Popen` is not recorded again.
    """

    def __init__(self) -> None:
        self.records: list[list[str]] = []
        self._run_depth = 0

    def install(self, monkeypatch) -> None:
        spy = self
        real_run = subprocess.run
        real_popen = subprocess.Popen

        def recording_run(*args, **kwargs):
            spy._record(args[0] if args else kwargs.get("args", []))
            spy._run_depth += 1
            try:
                return real_run(*args, **kwargs)
            finally:
                spy._run_depth -= 1

        class RecordingPopen(real_popen):  # type: ignore[misc, valid-type]
            def __init__(self, args, *rest, **kwargs):
                if not spy._run_depth:
                    spy._record(args)
                super().__init__(args, *rest, **kwargs)

        monkeypatch.setattr(subprocess, "run", recording_run)
        monkeypatch.setattr(subprocess, "Popen", RecordingPopen)

    def _record(self, args) -> None:
        argv = [args] if isinstance(args, (str, bytes, os.PathLike)) else list(args)
        self.records.append([os.fsdecode(token) for token in argv])

    def violations(self) -> list[list[str]]:
        return [argv for argv in self.records if forbidden_hits(argv)]
