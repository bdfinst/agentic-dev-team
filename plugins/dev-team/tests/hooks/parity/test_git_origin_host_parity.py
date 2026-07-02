"""Parity fixtures for scripts/git-origin-host (#613 / #572 Phase 3).

Runs the .sh and .py implementations against fixtures covering the script's
observable surface. assert_parity fails the merge on any byte-level divergence
in stdout, exit code, normalized stderr, or side-effect tree.

Unlike PreToolUse/PostToolUse hooks, git-origin-host reads its input from
argv[1] (an optional remote URL) rather than stdin — the fixture loader
consults ``argv.json`` when present.

Fixture layout (per subdirectory of fixtures/git_origin_host/):
    argv.json               - JSON list of extra argv tokens (optional)
    stdin.json              - stdin payload (unused by git-origin-host; kept
                              for harness symmetry)
    env.json                - {name: value} env overlay (optional)
    initial_tree/           - files copied into the sandbox before run
                              (the no_origin fixture uses a pre-inited .git)
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Dict, List

import pytest

from parity import Fixture, assert_parity  # type: ignore[import-not-found]


_REPO_ROOT = Path(__file__).resolve().parents[5]
_HOOK_SH = _REPO_ROOT / "plugins" / "dev-team" / "scripts" / "git-origin-host.sh"
_HOOK_PY = _REPO_ROOT / "plugins" / "dev-team" / "scripts" / "git_origin_host.py"
_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "git_origin_host"


def _load_fixture(dirpath: Path) -> Fixture:
    argv_path = dirpath / "argv.json"
    argv: List[str] = json.loads(argv_path.read_text()) if argv_path.is_file() else []
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
        stdin=b"",
        argv=argv,
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
    if shutil.which("git") is None:
        pytest.skip("git required for the no-origin fallback fixture")
    fixture = _load_fixture(fixture_dir)
    assert_parity(
        sh_argv=["bash", str(_HOOK_SH), *fixture.argv],
        py_argv=["python3", str(_HOOK_PY), *fixture.argv],
        fixture=fixture,
    )
