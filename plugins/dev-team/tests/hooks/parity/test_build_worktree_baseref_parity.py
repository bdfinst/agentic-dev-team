"""Parity fixtures for scripts/build-worktree-baseref (#587).

The .sh and .py implementations are CLI-only (no stdin). Fixtures set
`args.json` for argv (rather than `stdin.json`) and optionally an
`env.json`. Uses the same Fixture shape as the hook fixtures so the parity
harness picks it up unchanged.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Dict, List

import pytest

from parity import Fixture, assert_parity  # type: ignore[import-not-found]


_REPO_ROOT = Path(__file__).resolve().parents[5]
_SCRIPT_SH = (
    _REPO_ROOT / "plugins" / "dev-team" / "scripts" / "build-worktree-baseref.sh"
)
_SCRIPT_PY = (
    _REPO_ROOT / "plugins" / "dev-team" / "scripts" / "build_worktree_baseref.py"
)
_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "build_worktree_baseref"


def _load_fixture(dirpath: Path) -> Fixture:
    args: List[str] = []
    args_path = dirpath / "args.json"
    if args_path.is_file():
        args_raw = json.loads(args_path.read_text())
        if isinstance(args_raw, list):
            args = [str(a) for a in args_raw]
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
        argv=args,
        env=env,
        initial_tree=initial_tree,
    )


def _discover_fixtures() -> List[Path]:
    if not _FIXTURES_DIR.is_dir():
        return []
    return sorted(p for p in _FIXTURES_DIR.iterdir() if p.is_dir())


_FIXTURE_DIRS = _discover_fixtures()


@pytest.mark.skipif(
    not _SCRIPT_SH.is_file() or not _SCRIPT_PY.is_file(),
    reason="both .sh and .py implementations required",
)
@pytest.mark.skipif(not _FIXTURE_DIRS, reason="no fixture directories present")
@pytest.mark.parametrize("fixture_dir", _FIXTURE_DIRS, ids=lambda p: p.name)
def test_parity(fixture_dir: Path) -> None:
    if shutil.which("jq") is None:
        pytest.skip("jq required by the .sh")
    fixture = _load_fixture(fixture_dir)
    sh_argv = ["bash", str(_SCRIPT_SH)] + fixture.argv
    py_argv = ["python3", str(_SCRIPT_PY)] + fixture.argv
    # The parity harness's dispatch() runs argv verbatim (only substituting
    # the literal 'SANDBOX' token); it does not append fixture.argv itself
    # since it treats argv as the whole command. Pass a Fixture with argv=[]
    # to avoid double-appending.
    fixture_no_argv = Fixture(
        name=fixture.name,
        stdin=fixture.stdin,
        argv=[],
        env=fixture.env,
        initial_tree=fixture.initial_tree,
    )
    assert_parity(sh_argv=sh_argv, py_argv=py_argv, fixture=fixture_no_argv)
