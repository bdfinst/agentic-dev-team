"""Parity fixtures for scripts/build-wave (#611 / #572 Phase 3).

Runs the .sh and .py against fixture plans (copied from
``tests/fixtures/plans/``) and asserts byte-identical stdout, stderr,
exit code, and side-effect tree.

Each subdirectory of fixtures/build_wave/ contains an ``initial_tree/``
with the plan.md and any files it references. The plan is at the
sandbox root as ``plan.md`` so ``argv = ["plan.md"]`` works for both
implementations.

Note: build-wave.sh shells out to plan-waves.sh, which shells out to
inline Python for the DAG analysis. The port shells to the same
plan-waves.sh (byte-parity is what matters until plan-waves.sh itself
converts). Once plan-waves.py exists this test still passes.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Dict, List

import pytest

from parity import Fixture, assert_parity  # type: ignore[import-not-found]


_REPO_ROOT = Path(__file__).resolve().parents[5]
_HOOK_SH = _REPO_ROOT / "plugins" / "dev-team" / "scripts" / "build-wave.sh"
_HOOK_PY = _REPO_ROOT / "plugins" / "dev-team" / "scripts" / "build_wave.py"
_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "build_wave"


def _load_fixture(dirpath: Path) -> Fixture:
    argv_path = dirpath / "argv.json"
    argv: List[str] = (
        json.loads(argv_path.read_text()) if argv_path.is_file() else ["plan.md"]
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
        stdin=b"",
        argv=argv,
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
        pytest.skip("jq required by build-wave.sh")
    fixture = _load_fixture(fixture_dir)
    assert_parity(
        sh_argv=["bash", str(_HOOK_SH), *fixture.argv],
        py_argv=["python3", str(_HOOK_PY), *fixture.argv],
        fixture=fixture,
    )
