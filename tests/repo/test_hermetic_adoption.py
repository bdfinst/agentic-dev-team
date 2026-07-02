"""Enforces that every fixture bats file that does git operations sources
tests/lib/hermetic.bash and wires hermetic_setup + hermetic_teardown into
its setup()/teardown() blocks. Issue #546 — without this, fixtures inherit
git env vars git exports into pre-push hooks and corrupt the parent
worktree's refs.

Ported from tests/repo/hermetic_adoption_tests.bats (issue #671). bats-core
itself (and tests/lib/hermetic.bash with it) is now fully retired (#677,
closing epic #668) — there are no *.bats files left under tests/ for this
sensor to scan, so it now passes vacuously. Left in place rather than
deleted: it costs nothing to run and re-arms automatically if a *.bats file
ever reappears.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

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
        f"matters.\n" + "\n".join(f"  {o}" for o in offenders)
    )
