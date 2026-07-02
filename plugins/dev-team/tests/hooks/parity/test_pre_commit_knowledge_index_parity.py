"""Parity fixtures for hooks/pre_commit_knowledge_index (#582).

Full stale-detection behavior is exercised by the pytest unit tests
against a real git fixture repo. These parity fixtures cover only the
silent branches (non-commit, --no-verify bypass, malformed stdin,
unrelated tool) — branches that don't depend on a git surface in the
sandbox.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Dict, List

import pytest

from parity import Fixture, dispatch, _normalize_stderr  # type: ignore[import-not-found]


_REPO_ROOT = Path(__file__).resolve().parents[5]
_HOOK_SH = (
    _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "pre-commit-knowledge-index.sh"
)
_HOOK_PY = (
    _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "pre_commit_knowledge_index.py"
)
_FIXTURES_DIR = (
    Path(__file__).resolve().parent / "fixtures" / "pre_commit_knowledge_index"
)


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
    return Fixture(name=dirpath.name, stdin=stdin_bytes, argv=[], env=env)


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
def test_pre_commit_knowledge_index_parity(fixture_dir: Path) -> None:
    if shutil.which("jq") is None:
        pytest.skip("jq required by the .sh")
    fixture = _load_fixture(fixture_dir)
    sh = dispatch(["bash", str(_HOOK_SH)], stdin_bytes=fixture.stdin, env=fixture.env)
    py = dispatch(
        ["python3", str(_HOOK_PY)], stdin_bytes=fixture.stdin, env=fixture.env
    )
    assert sh.exit_code == py.exit_code, (
        f"[{fixture.name}] exit sh={sh.exit_code} py={py.exit_code}\n"
        f"sh stderr: {sh.stderr!r}\npy stderr: {py.stderr!r}"
    )
    assert sh.stdout == py.stdout, (
        f"[{fixture.name}] stdout sh={sh.stdout!r} py={py.stdout!r}"
    )
    sh_err = _normalize_stderr(sh.stderr, sh.sandbox_root)
    py_err = _normalize_stderr(py.stderr, py.sandbox_root)
    assert sh_err == py_err, (
        f"[{fixture.name}] stderr diverged\nsh: {sh_err!r}\npy: {py_err!r}"
    )
