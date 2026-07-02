"""Parity fixtures for scripts/build-jobs (#610 / #572 Phase 3).

Fixture layout (per subdirectory of fixtures/build_jobs/):
    argv.json               - JSON list of argv tokens
    env.json                - {name: value} env overlay
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import pytest

from parity import Fixture, assert_parity  # type: ignore[import-not-found]


_REPO_ROOT = Path(__file__).resolve().parents[5]
_HOOK_SH = _REPO_ROOT / "plugins" / "dev-team" / "scripts" / "build-jobs.sh"
_HOOK_PY = _REPO_ROOT / "plugins" / "dev-team" / "scripts" / "build_jobs.py"
_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "build_jobs"


def _load_fixture(dirpath: Path) -> Fixture:
    argv_path = dirpath / "argv.json"
    argv: List[str] = json.loads(argv_path.read_text()) if argv_path.is_file() else []
    env_path = dirpath / "env.json"
    env: Dict[str, str] = {}
    if env_path.is_file():
        env = {k: str(v) for k, v in json.loads(env_path.read_text()).items()}
    return Fixture(name=dirpath.name, stdin=b"", argv=argv, env=env, initial_tree={})


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
    fixture = _load_fixture(fixture_dir)
    assert_parity(
        sh_argv=["bash", str(_HOOK_SH), *fixture.argv],
        py_argv=["python3", str(_HOOK_PY), *fixture.argv],
        fixture=fixture,
    )
