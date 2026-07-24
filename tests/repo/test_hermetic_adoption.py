"""Enforces that every fixture bats file that does git operations sources
tests/lib/hermetic.bash and wires hermetic_setup + hermetic_teardown into
its setup()/teardown() blocks. Issue #546 — without this, fixtures inherit
git env vars git exports into pre-push hooks and corrupt the parent
worktree's refs.

Ported from tests/repo/hermetic_adoption_tests.bats (issue #671). bats-core
itself (and tests/lib/hermetic.bash with it) is now fully retired (#677,
closing epic #668) — there are no *.bats files left under tests/ for this
sensor to scan, so that half now passes vacuously. Left in place rather
than deleted: it costs nothing to run and re-arms automatically if a
*.bats file ever reappears.

Issue #715 — the bats-only, repo-root-`tests/`-only enumeration above was
blind to plugins/dev-team/tests/**/*.py, where four pytest files shelled
out to mutating `git` subprocess calls without scrubbing the same five
dangerous env vars. This module now also scans that pytest tree for
subprocess-based git mutation that doesn't route through the shared
plugins/dev-team/tests/lib/hermetic.hermetic_git_env() helper.
"""

from __future__ import annotations

import ast
import re

from _repo_root import REPO_ROOT

# Files that legitimately do NOT need hermetic_setup. Add one line per
# entry with a short rationale — no silent skips.
_WHITELIST: set[str] = set()

# Only lines that START with (optionally-indented) `git <mutating-verb>` count
# — this excludes JSON test payloads like `"command":"git commit -m x"` where
# the fixture is describing a git op the SUT will interpret, not running it.
#
# Mutating verbs: init, commit, push, update-ref, checkout, branch, tag,
# add, clone, fetch, pull, merge, rebase, reset, apply, cherry-pick,
# revert, worktree, stash. Read-only ops (log, rev-parse, for-each-ref,
# config --get) do not risk ref corruption and are ignored.
_MUTATING_GIT_RE = re.compile(
    r"^[ \t]*git[ \t]+(init|commit|push|update-ref|checkout|branch|tag|add|"
    r"clone|fetch|pull|merge|rebase|reset|apply|cherry-pick|revert|worktree|"
    r"stash)([ \t]|$)",
    re.MULTILINE,
)


def _needs_hermetic(text: str) -> bool:
    return bool(_MUTATING_GIT_RE.search(text))


def _is_hermetic(text: str) -> bool:
    return (
        "load '../lib/hermetic'" in text
        and "hermetic_setup" in text
        and "hermetic_teardown" in text
    )


def test_every_fixture_bats_file_that_runs_git_ops_loads_hermetic() -> None:
    offenders = []
    for f in sorted((REPO_ROOT / "tests").rglob("*.bats")):
        rel = f.relative_to(REPO_ROOT).as_posix()
        if rel in _WHITELIST:
            continue
        text = f.read_text()
        if not _needs_hermetic(text):
            continue
        if not _is_hermetic(text):
            offenders.append(rel)

    assert not offenders, (
        "The following bats files do fixture git operations but do not "
        "source tests/lib/hermetic.bash + wire "
        "hermetic_setup/hermetic_teardown. See issue #546 for why this "
        "matters.\n" + "\n".join(f"  {o}" for o in offenders)
    )


# ---------------------------------------------------------------------------
# Python-fixture equivalent (issue #715)
# ---------------------------------------------------------------------------

# Roots of pytest trees, outside tests/, that are known to shell out to
# mutating git subprocesses directly (not via tests/repo/conftest.py's
# hermetic_env fixture, which this scan does not need to duplicate). Add a
# new root here if another such tree is confirmed.
_PY_SCAN_ROOTS = ("plugins/dev-team/tests",)

# Same rationale as _WHITELIST above, for the Python-side scan.
_PY_WHITELIST: set[str] = set()

# The helper itself and its own unit test never need to be flagged: the
# helper defines hermetic_git_env() but doesn't call subprocess with git
# args, and its test only calls the helper, not subprocess.
_PY_SELF_EXEMPT = {
    "plugins/dev-team/tests/lib/hermetic.py",
    "plugins/dev-team/tests/lib/test_hermetic.py",
}

_PY_SUBPROCESS_FUNCS = {"run", "call", "check_call", "check_output", "Popen"}

# Kept in lockstep with _MUTATING_GIT_RE's verb list above.
_PY_MUTATING_VERBS = {
    "init",
    "commit",
    "push",
    "update-ref",
    "checkout",
    "branch",
    "tag",
    "add",
    "clone",
    "fetch",
    "pull",
    "merge",
    "rebase",
    "reset",
    "apply",
    "cherry-pick",
    "revert",
    "worktree",
    "stash",
}


def _iter_git_mutating_calls(tree: ast.AST):
    """Yield subprocess.* Call nodes whose first arg is a git-mutating argv."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            fname = func.attr
        elif isinstance(func, ast.Name):
            fname = func.id
        else:
            continue
        if fname not in _PY_SUBPROCESS_FUNCS:
            continue
        if not node.args:
            continue
        first = node.args[0]
        if not isinstance(first, (ast.List, ast.Tuple)):
            continue
        argv = [
            elt.value
            for elt in first.elts
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
        ]
        if len(argv) < 2 or argv[0] != "git" or argv[1] not in _PY_MUTATING_VERBS:
            continue
        yield node


def _needs_hermetic_py(text: str) -> bool:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False
    return any(True for _ in _iter_git_mutating_calls(tree))


def _is_hermetic_py(text: str) -> bool:
    """Best-effort static check (regex/AST, not full data-flow — #715 spec's
    documented tradeoff): the file must use the shared helper, AND every
    flagged git-mutating call site must pass an env= kwarg at all."""
    if "hermetic_git_env(" not in text:
        return False
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False
    for node in _iter_git_mutating_calls(tree):
        if not any(kw.arg == "env" for kw in node.keywords):
            return False
    return True


def test_every_python_fixture_that_runs_git_ops_uses_hermetic_env() -> None:
    offenders = []
    for root in _PY_SCAN_ROOTS:
        for f in sorted((REPO_ROOT / root).rglob("*.py")):
            rel = f.relative_to(REPO_ROOT).as_posix()
            if rel in _PY_WHITELIST or rel in _PY_SELF_EXEMPT:
                continue
            text = f.read_text()
            if not _needs_hermetic_py(text):
                continue
            if not _is_hermetic_py(text):
                offenders.append(rel)

    assert not offenders, (
        "The following pytest files shell out to mutating git subprocess "
        "calls but do not route every call through "
        "plugins/dev-team/tests/lib/hermetic.hermetic_git_env() (env= on "
        "every git-mutating call site). See issue #715 / #546 for why this "
        "matters.\n" + "\n".join(f"  {o}" for o in offenders)
    )
