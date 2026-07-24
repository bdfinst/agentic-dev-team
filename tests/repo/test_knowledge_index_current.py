"""CI freshness gate. The shipped knowledge/index.json must match
what a fresh build of the working tree would produce. This is the
strict net — anything that escapes the PostToolUse hook and the
pre-commit sibling hook is caught here.

Ported from tests/repo/knowledge_index_current.bats (issue #671).
"""

from __future__ import annotations

import subprocess
import sys

from _repo_root import REPO_ROOT

BUILDER = (
    REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib" / "build_knowledge_index.py"
)


def test_knowledge_index_is_current_with_working_tree() -> None:
    res = subprocess.run(
        [sys.executable, str(BUILDER), "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, res.stdout + res.stderr
