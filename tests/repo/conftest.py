"""Shared fixtures for tests/repo/ pytest ports.

REPO_ROOT anchors every test to the repository root regardless of the
pytest invocation's cwd. ``hermetic_env`` reproduces tests/lib/hermetic.bash's
scrubbing (issue #546) for tests that shell out to real ``git`` subprocesses:
callers pass the returned env dict to ``subprocess.run(..., env=...)`` so the
child process never inherits GIT_DIR/GIT_INDEX_FILE/etc. from the parent, and
never reads the real user's ~/.gitconfig.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def hermetic_env(tmp_path: Path) -> dict[str, str]:
    """A minimal, scrubbed environment for subprocess git operations.

    Mirrors hermetic_setup() in tests/lib/hermetic.bash: no inherited
    GIT_DIR/GIT_INDEX_FILE/GIT_WORK_TREE/GIT_PREFIX/GIT_REFLOG_ACTION, and
    global/system git config redirected to /dev/null so ~/.gitconfig can't
    bleed into the test.
    """
    env = {
        k: v
        for k, v in os.environ.items()
        if k
        not in (
            "GIT_DIR",
            "GIT_INDEX_FILE",
            "GIT_WORK_TREE",
            "GIT_PREFIX",
            "GIT_REFLOG_ACTION",
        )
    }
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    env["GIT_CONFIG_SYSTEM"] = "/dev/null"
    env["HOME"] = str(tmp_path)
    return env
