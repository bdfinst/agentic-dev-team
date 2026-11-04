"""Fixtures and recorders for tests/scripts/test_lane*.py.

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
import shlex
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

_SCRIPTS_DIR = REPO_ROOT / "plugins" / "dev-team" / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import lane
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

#: Spellings the exact-token set cannot see: its long options. Derived from
#: the oracle set above, not read from lane_core, so the oracle stays independent.
ORACLE_LONG_OPTIONS = tuple(
    sorted(token for token in ORACLE_FORBIDDEN_TOKENS if token.startswith("--"))
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


#: Written out here, not read from lane_core: a hermetic test environment must
#: not depend on the code under test to say what reconfigures git. Together
#: with the five variables `hermetic_git_env` drops.
EXTRA_DROPPED_GIT_VARIABLES = frozenset(
    {
        "GIT_CONFIG_COUNT",
        "GIT_CONFIG_PARAMETERS",
        "GIT_COMMON_DIR",
        "GIT_NAMESPACE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_EXEC_PATH",
        "GIT_ATTR_SOURCE",
        "GIT_REPLACE_REF_BASE",
        "GIT_NO_REPLACE_OBJECTS",
    }
)
DROPPED_GIT_VARIABLE_PREFIXES = ("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")


def git_env(home: Path) -> dict[str, str]:
    """Hermetic git environment with a fixed commit identity."""
    base = hermetic_git_env(home=home)
    kept = {
        key: value
        for key, value in base.items()
        if key not in EXTRA_DROPPED_GIT_VARIABLES
        and not key.startswith(DROPPED_GIT_VARIABLE_PREFIXES)
    }
    return {**kept, **_IDENTITY}


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


def git_succeeds(cwd: Path, *args: str) -> bool:
    """Whether a fixture git command exits 0 (hermetic env); never raises on exit 1."""
    done = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=git_env(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    return done.returncode == 0


def run_main(argv, cwd, capsys):
    """Run `lane.main` in-process; return `(exit code, stdout, stderr)`."""
    code = lane.main(argv, cwd=cwd)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


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


def unchanged_state(cwd: Path) -> dict[str, str]:
    """What must be equal before and after a refused command run in `cwd`.

    All refs, the worktree list, HEAD and its tree, the index (mode, object and
    stage of every entry) and the working tree (`status`, ignored files too).
    """
    return {
        "refs": git(cwd, "for-each-ref"),
        "worktrees": git(cwd, "worktree", "list", "--porcelain"),
        "head": git(cwd, "rev-parse", "HEAD"),
        "tree": git(cwd, "rev-parse", "HEAD^{tree}"),
        "index": git(cwd, "ls-files", "--stage"),
        "status": git(cwd, "status", "--porcelain=v1", "--ignored"),
    }


def has_unfinished_merge(cwd: Path) -> bool:
    """True when `cwd` has a merge underway or unmerged index entries."""
    return git_succeeds(cwd, "rev-parse", "--verify", "--quiet", "MERGE_HEAD") or (
        git(cwd, "ls-files", "-u") != ""
    )


def is_ancestor(cwd: Path, ancestor: str, descendant: str) -> bool:
    """The fixture-level oracle for ancestry, independent of `lane_core`."""
    return git_succeeds(cwd, "merge-base", "--is-ancestor", ancestor, descendant)


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


@pytest.fixture
def plain_directory(tmp_path, monkeypatch) -> Path:
    """A directory outside any repository, whatever lies above the temp directory."""
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    plain = tmp_path / "plain"
    plain.mkdir()
    return plain


# --- builders and probes for the compose tests ------------------------------


def lane_with_commit(repo: Repo, name: str = "feature") -> Path:
    """A lane beside `repo` with one commit of its own."""
    lane_path = add_linked_worktree(repo, name)
    commit_file(lane_path, "lane.txt", "lane\n", "lane work")
    return lane_path


def open_origin_lane(repo: Repo, name: str = "feature") -> Path:
    """A lane in a repository with an origin, branched from origin/main, with a commit."""
    lane_path = add_linked_worktree(repo, name, start="origin/main")
    commit_file(lane_path, "lane.txt", "lane\n", "lane work")
    return lane_path


def advance_trunk(repo: Repo, name: str = "trunk.txt", content: str = "trunk\n") -> str:
    """A new commit on the primary checkout's trunk branch; returns its SHA."""
    return commit_file(repo.path, name, content, f"trunk writes {name}")


def conflicting_lane(repo: Repo, with_origin: bool = False) -> Path:
    """A lane and the trunk both edit `base.txt`, so merging trunk conflicts.

    With an origin the lane starts at `origin/main`, which also moves ahead (a
    merge with no conflict), and only local `main` carries the conflicting edit.
    """
    lane_path = add_linked_worktree(
        repo, "feature", start="origin/main" if with_origin else TRUNK
    )
    commit_file(lane_path, "base.txt", "lane edit\n", "lane edits base")
    if with_origin:
        advance_origin(repo)
    advance_trunk(repo, "base.txt", "trunk edit\n")
    return lane_path


def advance_origin(repo: Repo, name: str = "remote.txt") -> str:
    """Move the bare origin's main forward without pushing, then fetch it."""
    scratch = Path(tempfile.mkdtemp(dir=repo.path.parent, prefix="origin-work-"))
    git(repo.path.parent, "clone", "-q", str(repo.origin), str(scratch))
    tip = commit_file(scratch, name, "remote\n", f"origin adds {name}")
    git(repo.origin, "fetch", "-q", str(scratch), "main:main")
    git(repo.path, "fetch", "-q", "origin")
    return tip


def install_hook(repo: Repo, name: str, script: str) -> Path:
    """An executable hook in the common git directory (never `core.hooksPath`)."""
    common = Path(repo.path, git(repo.path, "rev-parse", "--git-common-dir"))
    hook = common / "hooks" / name
    hook.parent.mkdir(exist_ok=True)
    hook.write_text(script, encoding="utf-8")
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR)
    return hook


HOOK_SENTINEL = "LANE-HOOK-REJECT"
REJECT_HOOK = f"#!/bin/sh\necho {HOOK_SENTINEL} >&2\nexit 1\n"
FAILING_MERGE_NUMBER = 2


def rejecting_nth_merge_hook(hook_call_log: Path) -> str:
    """A hook that logs every call and rejects the `FAILING_MERGE_NUMBER`th."""
    log = shlex.quote(str(hook_call_log))
    return (
        f"#!/bin/sh\necho call >> {log}\n"
        f'[ "$(grep -c call {log})" -lt {FAILING_MERGE_NUMBER} ] && exit 0\n'
        f"echo {HOOK_SENTINEL} >&2\nexit 1\n"
    )


def merge_argvs(argv_spy: ArgvSpy, start: int) -> list[list[str]]:
    """Recorded `git merge <target>` invocations after record index `start`.

    `merge --abort` is a merge command too, but it merges nothing.
    """
    return [
        argv
        for argv in argv_spy.records[start:]
        if argv[:2] == ["git", "merge"] and "--abort" not in argv
    ]


def stub_git_call(
    monkeypatch,
    name: str,
    prefixes: Sequence[Sequence[str]],
    outcome: Callable[[], object],
) -> None:
    """Make `lane_core.<name>` return `outcome()` for a call whose arguments start
    with one of `prefixes`; every other call runs for real."""
    real = getattr(lane_core, name)

    def stubbed(args, cwd):
        if any(list(args[: len(prefix)]) == list(prefix) for prefix in prefixes):
            return outcome()
        return real(args, cwd)

    monkeypatch.setattr(lane_core, name, stubbed)


def fail_git_ok_for(monkeypatch, *prefixes: Sequence[str]) -> None:
    """`lane_core.git_ok` reports failure, and runs nothing, for these argument prefixes."""
    stub_git_call(monkeypatch, "git_ok", prefixes, lambda: False)
