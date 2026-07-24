"""Building the knowledge index must leave no temp-file leak — the
builder publishes atomically (temp file + rename), and on success the
only artifact in the output directory is the index itself.

This builds into an ISOLATED output (the KNOWLEDGE_INDEX_OUTPUT test seam)
rather than rewriting the canonical plugins/dev-team/knowledge/index.json
in place. That keeps the test parallel-safe (no shared mutable repo file
that concurrent readers might catch mid-write) and lets it run
unconditionally instead of skipping whenever the working tree is dirty.
Correctness of the real corpus build is cross-checked against the
committed index byte-for-byte.

Ported from tests/repo/knowledge_index_no_leak.bats (issue #671).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from _repo_root import REPO_ROOT

BUILDER = (
    REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib" / "build_knowledge_index.py"
)
COMMITTED_INDEX = REPO_ROOT / "plugins" / "dev-team" / "knowledge" / "index.json"


def _build(out: Path) -> None:
    env = {**os.environ, "KNOWLEDGE_INDEX_OUTPUT": str(out)}
    subprocess.run([sys.executable, str(BUILDER)], env=env, check=True)


def test_rebuild_leaves_no_temp_or_partial_files_beside_the_index(
    tmp_path: Path,
) -> None:
    out = tmp_path / "index.json"
    # Default corpus roots (the real plugin tree) → output diverted to tmp_path.
    _build(out)
    # On a clean publish the temp file has been renamed onto the index; the
    # only thing left in the directory is the index itself.
    assert os.listdir(tmp_path) == ["index.json"]


def test_diverted_build_is_byte_identical_to_committed_index(tmp_path: Path) -> None:
    out = tmp_path / "index.json"
    _build(out)
    assert out.read_bytes() == COMMITTED_INDEX.read_bytes()
