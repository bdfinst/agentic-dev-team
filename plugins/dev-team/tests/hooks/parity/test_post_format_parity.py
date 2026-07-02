"""Parity fixtures for hooks/post-format (#601).

Each fixture exercises a code path where both bash and Python must silently
exit 0:

  empty_stdin       — no stdin body; hook returns 0.
  missing_file_path — tool_input has no file_path; hook returns 0.
  file_not_exists   — file_path present but file absent; hook returns 0.
  malformed_json    — invalid JSON; jq/Python both return 0 (advisory fail).
  windows_path_cwd  — C:\\-style path (also absent); hook returns 0.

Formatter side-effects are deliberately kept OUT of these fixtures — the hook
shells out to prettier/ruff/etc. only when the file exists on disk, which
none of these fixtures produce. That keeps the parity check purely about the
dispatch/guard logic, not about whether a formatter happens to be installed.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Dict, List

import pytest

from parity import Fixture, assert_parity  # type: ignore[import-not-found]


_REPO_ROOT = Path(__file__).resolve().parents[5]
_HOOK_SH = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "post-format.sh"
_HOOK_PY = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "post_format.py"
_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "post_format"


def _load_fixture(dirpath: Path) -> Fixture:
    stdin_path = dirpath / "stdin.json"
    stdin_bytes = stdin_path.read_bytes() if stdin_path.is_file() else b""
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
def test_parity(fixture_dir: Path) -> None:
    if shutil.which("jq") is None:
        pytest.skip("jq required by the .sh")
    fixture = _load_fixture(fixture_dir)
    assert_parity(
        sh_argv=["bash", str(_HOOK_SH)],
        py_argv=["python3", str(_HOOK_PY)],
        fixture=fixture,
    )
