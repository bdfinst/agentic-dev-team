"""Parity fixtures for hooks/skills-index (#604).

Seven fixtures span every branch of the dispatch tree plus the two builder
outcomes:

  non_skill_edit_silent       — Edit to a non-SKILL.md file → silent pass.
  non_edit_tool_silent        — Read of a SKILL.md → silent pass.
  malformed_json_silent       — invalid JSON stdin → silent pass.
  empty_stdin_silent          — empty stdin → silent pass.
  windows_style_skill_path    — backslash-heavy file_path does not match the
                                Unix-slash SKILL.md regex → silent pass.
  skill_edit_rebuild_success  — SKILL.md Edit with stubbed builder that exits
                                0 → `[skills-index] rebuilt` on stderr.
  skill_edit_rebuild_failure  — SKILL.md Edit with stubbed builder that
                                writes to stderr and exits 1 → the first
                                line of stderr is quoted in the failure
                                message.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Dict, List

import pytest

from parity import Fixture, assert_parity  # type: ignore[import-not-found]


_REPO_ROOT = Path(__file__).resolve().parents[5]
_HOOK_SH = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "skills-index.sh"
_HOOK_PY = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "skills_index.py"
_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "skills_index"


def _load_fixture(dirpath: Path) -> Fixture:
    stdin_path = dirpath / "stdin.json"
    stdin_bytes = stdin_path.read_bytes() if stdin_path.is_file() else b""
    env_path = dirpath / "env.json"
    env: Dict[str, str] = {}
    if env_path.is_file():
        env = {k: str(v) for k, v in json.loads(env_path.read_text()).items()}
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
        env=env,
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
