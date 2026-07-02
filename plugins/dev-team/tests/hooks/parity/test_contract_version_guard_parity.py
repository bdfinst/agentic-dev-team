"""Parity fixtures for hooks/contract-version-guard (#596).

Runs the .sh and .py implementations against six fixture directories under
fixtures/contract_version_guard/. assert_parity fails the merge on any
byte-level divergence in stdout, exit code, normalized stderr, or side-effect
tree.

Fixture layout (per subdirectory of fixtures/contract_version_guard/):
    stdin.json              - stdin payload for the hook (required, may be
                              empty)
    env.json                - {name: value} env overlay (optional)
    initial_tree/           - files copied into the sandbox root before run
                              (unused here — the hook does not read the
                              sandbox; it queries the plugin repo HEAD)

Note: this hook resolves REPO_ROOT from its own script path, not from CWD,
so all sandbox scenarios that reach the git-show step will observe the
plugin repo's real HEAD content. The six fixtures selected below are all
early-exit paths (non-contract file, missing file_path, malformed stdin,
release-please bypass, empty stdin, malformed Edit shape) that block or
allow BEFORE the git-show step and are therefore stable across environments.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Dict, List

import pytest

from parity import Fixture, assert_parity  # type: ignore[import-not-found]


_REPO_ROOT = Path(__file__).resolve().parents[5]
_HOOK_SH = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "contract-version-guard.sh"
_HOOK_PY = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "contract_version_guard.py"
_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "contract_version_guard"


def _load_fixture(dirpath: Path) -> Fixture:
    stdin_bytes = (
        (dirpath / "stdin.json").read_bytes()
        if (dirpath / "stdin.json").is_file()
        else b""
    )
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
