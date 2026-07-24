"""Shared hermetic-env helper for plugins/dev-team/tests/ pytest fixtures.

Issue #715: pytest fixtures under plugins/dev-team/tests/ that shell out to
mutating `git` subprocesses (init, add, commit, ...) must not inherit the
five git-exported env vars a pre-push hook's own git invocation sets
(GIT_DIR, GIT_INDEX_FILE, GIT_WORK_TREE, GIT_PREFIX, GIT_REFLOG_ACTION) —
otherwise the fixture's "git init"/"git commit" can be redirected into the
*parent* worktree/index instead of the fixture's own tmp_path, corrupting
real refs. This mirrors tests/repo/conftest.py's `hermetic_env` fixture
(issue #546) as a plain importable function so tests outside tests/repo/
(which has no conftest.py of its own) get the same guarantee.
"""

from __future__ import annotations

import os
from pathlib import Path

_DANGEROUS_GIT_VARS = (
    "GIT_DIR",
    "GIT_INDEX_FILE",
    "GIT_WORK_TREE",
    "GIT_PREFIX",
    "GIT_REFLOG_ACTION",
)


def hermetic_git_env(home: Path | None = None) -> dict[str, str]:
    """Return an environment safe to pass to subprocess git mutations.

    Strips the five dangerous git-exported vars so a fixture's own `git`
    subprocess calls can never be redirected into the parent worktree, and
    redirects global/system git config to /dev/null so the real user's
    ~/.gitconfig can't bleed into the test. Pass `home` (typically the
    fixture's `tmp_path`) to also isolate HOME for tests that care.
    """
    env = {k: v for k, v in os.environ.items() if k not in _DANGEROUS_GIT_VARS}
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    env["GIT_CONFIG_SYSTEM"] = "/dev/null"
    if home is not None:
        env["HOME"] = str(home)
    return env
