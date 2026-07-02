"""The knowledge-index builder must publish the index ATOMICALLY.

Why: under parallel test runs, one process rebuilds the index while
another reads it. A truncate-then-stream write (`Path.write_text`) leaves
a window where a concurrent reader observes an empty or partial file and a
real key looks "missing". The only correct fix for unsynchronized readers
is an atomic publish: build into a sibling temp file, then rename it over
the destination. `os.replace` does exactly that — and its observable
signature is that the destination path's inode is SWAPPED on each rebuild
(a truncate-in-place keeps the same inode). These tests assert that
signature deterministically, so we don't depend on catching a timing race.

Ported from tests/repo/knowledge_index_atomic_write.bats (issue #671).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILDER = (
    REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib" / "build_knowledge_index.py"
)
SENTINEL = "plugins/dev-team/knowledge/agent-registry.md"


def _build(out: Path) -> None:
    env = {**os.environ, "KNOWLEDGE_INDEX_OUTPUT": str(out)}
    subprocess.run([sys.executable, str(BUILDER)], env=env, check=True)


def test_rebuild_swaps_index_inode(tmp_path: Path) -> None:
    out = tmp_path / "index.json"
    _build(out)
    before = out.stat().st_ino
    _build(out)
    after = out.stat().st_ino
    assert before != after, (
        f"inode unchanged ({before}): index was rewritten in place, not atomically replaced"
    )


def test_destination_always_complete_sentinel_present_after_each_rebuild(
    tmp_path: Path,
) -> None:
    out = tmp_path / "index.json"
    _build(out)
    data = json.loads(out.read_text())
    assert SENTINEL in data
    # A second rebuild must also leave a complete, parseable file behind.
    _build(out)
    data = json.loads(out.read_text())
    assert SENTINEL in data
