"""Parity fixtures for hooks/codegraph_bootstrap (#592).

The bootstrap hook writes nothing to stdout by contract — nudges go on
stderr. Both impls also spawn a detached child process for the real
build path; the parity fixtures avoid that path (no `.codegraph` dir OR
CODEGRAPH_BIN set to a non-existent path) so the child spawn is not
exercised. The .sh's foreground path (CODEGRAPH_BOOTSTRAP_SYNC=1) IS
exercised by the pytest unit tests.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Dict, List

import pytest

from parity import Fixture, dispatch, _normalize_stderr  # type: ignore[import-not-found]


_REPO_ROOT = Path(__file__).resolve().parents[5]
_HOOK_SH = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "codegraph-bootstrap.sh"
_HOOK_PY = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "codegraph_bootstrap.py"
_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "codegraph_bootstrap"


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
        for p in tree_root.rglob("*"):
            if p.is_file():
                initial_tree[str(p.relative_to(tree_root))] = p.read_text()
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
def test_codegraph_bootstrap_parity(fixture_dir: Path) -> None:
    if shutil.which("jq") is None:
        pytest.skip("jq required by the .sh")
    fixture = _load_fixture(fixture_dir)
    sh_result = dispatch(
        ["bash", str(_HOOK_SH)],
        stdin_bytes=fixture.stdin,
        env=fixture.env,
        initial_tree=fixture.initial_tree,
    )
    py_result = dispatch(
        ["python3", str(_HOOK_PY)],
        stdin_bytes=fixture.stdin,
        env=fixture.env,
        initial_tree=fixture.initial_tree,
    )
    assert sh_result.exit_code == py_result.exit_code == 0, (
        f"[{fixture.name}] exit sh={sh_result.exit_code} py={py_result.exit_code}"
    )
    assert sh_result.stdout == py_result.stdout == b"", (
        f"[{fixture.name}] stdout diverged: sh={sh_result.stdout!r} py={py_result.stdout!r}"
    )
    sh_err = _normalize_stderr(sh_result.stderr, sh_result.sandbox_root)
    py_err = _normalize_stderr(py_result.stderr, py_result.sandbox_root)
    assert sh_err == py_err, (
        f"[{fixture.name}] stderr diverged\nsh: {sh_err!r}\npy: {py_err!r}"
    )
