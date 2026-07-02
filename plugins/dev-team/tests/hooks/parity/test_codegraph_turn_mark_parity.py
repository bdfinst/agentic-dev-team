"""Parity fixtures for hooks/codegraph-turn-mark (#594).

Runs the .sh and .py implementations against the six fixture directories
under fixtures/codegraph_turn_mark/. assert_parity fails the merge on any
byte-level divergence in stdout, exit code, normalized stderr, or the
side-effect tree (which for this hook is the atomic sentinel write under
.claude/codegraph-turn-state.json).

Fixture layout (per subdirectory of fixtures/codegraph_turn_mark/):
    stdin.json              - stdin payload for the hook (required, may be empty)
    initial_tree/           - files copied into the sandbox root before run
                              (typically the transcript.jsonl the hook reads)
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Dict, List

import pytest

from parity import Fixture, assert_parity  # type: ignore[import-not-found]


_REPO_ROOT = Path(__file__).resolve().parents[5]
_HOOK_SH = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "codegraph-turn-mark.sh"
_HOOK_PY = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "codegraph_turn_mark.py"
_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "codegraph_turn_mark"


def _load_fixture(dirpath: Path) -> Fixture:
    stdin_bytes = (
        (dirpath / "stdin.json").read_bytes()
        if (dirpath / "stdin.json").is_file()
        else b""
    )
    initial_tree: Dict[str, str] = {}
    tree_root = dirpath / "initial_tree"
    if tree_root.is_dir():
        for path in tree_root.rglob("*"):
            if path.is_file():
                rel = str(path.relative_to(tree_root))
                initial_tree[rel] = path.read_text()
    return Fixture(
        name=dirpath.name,
        stdin=stdin_bytes,
        argv=[],
        env={},
        initial_tree=initial_tree,
    )


def _discover_fixtures() -> List[Path]:
    if not _FIXTURES_DIR.is_dir():
        return []
    return sorted(p for p in _FIXTURES_DIR.iterdir() if p.is_dir())


_FIXTURE_DIRS = _discover_fixtures()


@pytest.mark.skipif(
    not _HOOK_SH.is_file() or not _HOOK_PY.is_file(),
    reason="both .sh and .py implementations required",
)
@pytest.mark.skipif(not _FIXTURE_DIRS, reason="no fixture directories present")
@pytest.mark.parametrize("fixture_dir", _FIXTURE_DIRS, ids=lambda p: p.name)
def test_parity(fixture_dir: Path) -> None:
    if shutil.which("jq") is None:
        pytest.skip("jq required by the .sh")
    fixture = _load_fixture(fixture_dir)
    assert_parity(
        sh_argv=["bash", str(_HOOK_SH)],
        py_argv=["python3", str(_HOOK_PY)],
        fixture=fixture,
    )
