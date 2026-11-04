"""Fixtures and recorders for tests/scripts/test_lane.py and test_lane_core.py.

`repo_without_remote`: a repository with no remote, trunk `main`.
`repo_with_origin`: a repository with a non-github bare `origin` (built with
`git clone --bare`), remote-tracking trunk `origin/main` equal to local `main`.

Both commit a `.gitignore` containing `.claude/` on trunk before any lane
exists, so gate and ledger files never make a lane dirty.

The autouse fixtures here (`hermetic_process_env`, `argv_spy`,
`enforce_covers`) apply only to a test module that imports them by name.

Named without a leading `test_` so pytest does not collect it. Not a conftest:
a plain importable module, like `_mutation_test_helpers.py`.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

_SCRIPTS_DIR = REPO_ROOT / "plugins" / "dev-team" / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import lane_core

_HERMETIC_DIR = REPO_ROOT / "plugins" / "dev-team" / "tests" / "lib"
if str(_HERMETIC_DIR) not in sys.path:
    sys.path.insert(0, str(_HERMETIC_DIR))

from hermetic import hermetic_git_env  # type: ignore[import-not-found]

TRUNK = "main"
GITIGNORE = ".claude/\n"
GIT_FAILED = "git command failed"
LANE_DIR_INFIX = "-lane-"

#: The oracle for "never pushes, never skips hooks". Deliberately written out
#: here instead of imported from lane_core: a test must not trust the code it
#: checks to define what is forbidden. Exact token equality, never substring.
ORACLE_FORBIDDEN_TOKENS = frozenset(
    {
        "push",
        "send-pack",
        "--no-verify",
        "--force",
        "--force-with-lease",
        "--force-if-includes",
        "-f",
        "--no-gpg-sign",
    }
)
ORACLE_HOOKS_PATH_PREFIX = "core.hookspath="
ORACLE_FORCE_REFSPEC_PREFIX = "+"

#: Spellings the exact-token set cannot see. Each is written out here, not read
#: from lane_core, for the same reason as the set above.
ORACLE_LONG_OPTIONS = (
    "--no-verify",
    "--force",
    "--force-with-lease",
    "--force-if-includes",
    "--no-gpg-sign",
)
ORACLE_MIN_ABBREVIATION = 3
ORACLE_CLUSTER = re.compile(r"-[A-Za-z]+")
ORACLE_NO_VERIFY_SUBCOMMANDS = frozenset({"commit", "merge", "am", "rebase"})
ORACLE_FORCE_UPPER_SUBCOMMANDS = frozenset({"branch", "worktree", "checkout", "switch"})
ORACLE_FORCE_UPPER_LETTERS = frozenset("DMBC")

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
    """Declare that this test renders a refusal block with this `what`.

    A real pytest marker: `enforce_covers` fails the test at its own teardown
    when it did not render that block. The decorator call is also read from the
    source (AST) by `covered_whats`, so the registry check does not depend on
    selection, execution order or xdist.
    """
    return pytest.mark.covers(what)


def covered_whats(paths: Iterable[Path]) -> set[str]:
    """Every `@covers("<what>")` literal in the given test sources."""
    whats: set[str] = set()
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and getattr(node.func, "id", None) == "covers"
            ):
                whats.update(
                    arg.value for arg in node.args if isinstance(arg, ast.Constant)
                )
    return whats


SKIP_MARK_NAMES = frozenset({"skip", "skipif", "xfail"})


def skipped_covers_in(source: str) -> list[str]:
    """Names of tests that declare `@covers(...)` and also a skip/skipif/xfail mark.

    A skipped test renders nothing, so its `covers` claim would be a lie the
    registry check cannot see from the source alone.
    """
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        decorators = [ast.unparse(decorator) for decorator in node.decorator_list]
        declares = any(text.startswith("covers(") for text in decorators)
        skips = any(
            f"mark.{name}" in text for text in decorators for name in SKIP_MARK_NAMES
        )
        if declares and skips:
            found.append(node.name)
    return found


def skipped_covers(paths: Iterable[Path]) -> list[str]:
    return [
        name
        for path in paths
        for name in skipped_covers_in(path.read_text(encoding="utf-8"))
    ]


@dataclass(frozen=True)
class Repo:
    """A fixture repository. `origin` is the bare repository, or None."""

    path: Path
    origin: Path | None


def build_repo_without_remote(root: Path) -> Repo:
    """No remote, trunk `main`, `.claude/` ignored."""
    path = root / "repo"
    path.mkdir()
    git(path, "init", "-q", "-b", TRUNK, home=root)
    commit_file(path, "base.txt", "base\n", "base")
    commit_file(path, ".gitignore", GITIGNORE, "ignore .claude")
    return Repo(path=path, origin=None)


def bare_clone_of(source: Path, dest: Path, home: Path) -> Path:
    """`git clone --bare source dest`; return `dest`."""
    git(home, "clone", "-q", "--bare", str(source), str(dest), home=home)
    return dest


def build_repo_with_origin(root: Path) -> Repo:
    """`build_repo_without_remote` plus a bare non-github `origin` at the same tip."""
    repo = build_repo_without_remote(root)
    origin = bare_clone_of(repo.path, root / "origin.git", root)
    git(repo.path, "remote", "add", "origin", str(origin))
    git(repo.path, "fetch", "-q", "origin")
    return Repo(path=repo.path, origin=origin)


def parse_output(stdout: str) -> dict[str, str]:
    """Split `key: value` success lines into a dict."""
    return dict(line.split(": ", 1) for line in stdout.splitlines() if ": " in line)


def default_lane_dir(repo: Repo, dashed_name: str) -> Path:
    """Where `open` puts a lane by default: beside the primary checkout."""
    name = f"{repo.path.name}{LANE_DIR_INFIX}{dashed_name}"
    return (repo.path.parent / name).resolve()


def add_linked_worktree(repo: Repo, branch: str, start: str = TRUNK) -> Path:
    """A linked worktree on a new `branch`, placed beside the primary checkout."""
    path = default_lane_dir(repo, branch.replace("/", "-"))
    git(repo.path, "worktree", "add", "-q", "-b", branch, str(path), start)
    return path


def lane_state(cwd: Path) -> tuple[str, str]:
    """All refs and the worktree list: equal before and after a refused open."""
    return (
        git(cwd, "for-each-ref"),
        git(cwd, "worktree", "list", "--porcelain"),
    )


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


def imported_modules(path: Path) -> set[str]:
    """Top-level names of every module `path` imports; relative imports fail."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            assert node.level == 0, "relative import"
            modules.add((node.module or "").split(".")[0])
    return modules


def non_stdlib(modules: set[str]) -> set[str]:
    return {name for name in modules if name not in sys.stdlib_module_names}


def single_refusal(code, out, err, what):
    """Assert one complete refusal block (three non-empty fields) and exit 1."""
    (block,) = parse_blocks(err)
    assert code == 1
    assert out == ""
    assert block["refused"] == what
    assert block["why"].strip() != ""
    assert block["how"].strip() != ""
    return block


def _spelling_hit(token: str, argv: Sequence[str]) -> bool:
    """An abbreviated long option, or a short-option cluster that forces or skips."""
    name = token.partition("=")[0]
    if (
        name.startswith("--")
        and len(name) - 2 >= ORACLE_MIN_ABBREVIATION
        and any(option.startswith(name) for option in ORACLE_LONG_OPTIONS)
    ):
        return True
    if ORACLE_CLUSTER.fullmatch(token) is None:
        return False
    letters = set(token[1:])
    words = set(argv)
    return (
        "f" in letters
        or ("n" in letters and bool(words & ORACLE_NO_VERIFY_SUBCOMMANDS))
        or (
            bool(letters & ORACLE_FORCE_UPPER_LETTERS)
            and bool(words & ORACLE_FORCE_UPPER_SUBCOMMANDS)
        )
    )


def forbidden_hits(argv: Sequence[str]) -> list[str]:
    """Tokens of one recorded argv that the tool must never pass."""
    return [
        token
        for token in argv
        if token in ORACLE_FORBIDDEN_TOKENS
        or token.partition("=")[0] in ORACLE_FORBIDDEN_TOKENS
        or token.lower() == ORACLE_HOOKS_PATH_PREFIX.rstrip("=")
        or token.lower().startswith(ORACLE_HOOKS_PATH_PREFIX)
        or token.startswith(ORACLE_FORCE_REFSPEC_PREFIX)
        or _spelling_hit(token, argv)
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


# --- fixtures imported by name into a test module ---------------------------


@pytest.fixture(autouse=True)
def hermetic_process_env(monkeypatch, tmp_path):
    """The code under test inherits the process env: make it hermetic too."""
    hermetic = git_env(tmp_path)
    for key in set(os.environ) - set(hermetic):
        monkeypatch.delenv(key)
    for key, value in hermetic.items():
        monkeypatch.setenv(key, value)


@pytest.fixture(autouse=True)
def argv_spy(monkeypatch, hermetic_process_env):
    """Record every argv; the forbidden set is asserted in this test's teardown."""
    spy = ArgvSpy()
    spy.install(monkeypatch)
    yield spy
    assert spy.violations() == [], "a recorded git call pushed, forced or skipped hooks"


@pytest.fixture(autouse=True)
def enforce_covers(request, monkeypatch):
    """Fail a test whose `covers` marker names a refusal it did not render.

    Per test, in the test's own teardown: no state is shared between tests, so
    it holds for any selection, order and xdist worker.
    """
    declared = {mark.args[0] for mark in request.node.iter_markers("covers")}
    rendered: set[str] = set()
    real = lane_core.render_block

    def recording(refusal):
        rendered.add(refusal.what)
        return real(refusal)

    monkeypatch.setattr(lane_core, "render_block", recording)
    yield
    assert declared <= rendered, (
        f"declared via covers but not rendered by this test: "
        f"{sorted(declared - rendered)}"
    )


@pytest.fixture
def repo_without_remote(tmp_path) -> Repo:
    return build_repo_without_remote(tmp_path)


@pytest.fixture
def repo_with_origin(tmp_path) -> Repo:
    return build_repo_with_origin(tmp_path)


@pytest.fixture
def repo_without_default_branch(tmp_path) -> Path:
    """No remote and no `main`: nothing for a default trunk to resolve to."""
    path = tmp_path / "odd"
    path.mkdir()
    git(path, "init", "-q", "-b", "elsewhere", home=tmp_path)
    commit_file(path, "a.txt", "a\n", "a")
    return path
