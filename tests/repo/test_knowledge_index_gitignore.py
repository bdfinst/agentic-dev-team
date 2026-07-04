"""The knowledge index is checked into git and not gitignored.

Ported from tests/repo/knowledge_index_gitignore.bats (issue #671).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INDEX_PATH = "plugins/dev-team/knowledge/index.json"


def test_knowledge_index_is_tracked_by_git() -> None:
    res = subprocess.run(
        ["git", "ls-files", INDEX_PATH],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert res.stdout.strip() == INDEX_PATH


def test_knowledge_index_is_not_gitignored() -> None:
    # git check-ignore exits 0 when ignored, 1 when NOT ignored.
    res = subprocess.run(
        ["git", "check-ignore", INDEX_PATH],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert res.returncode != 0
