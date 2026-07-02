"""Parity fixtures for hooks/pre-tool-guard (#602).

Six fixtures spanning the full observable surface:

  blocked_env_file   — file_path=.env → exit 2 with BLOCKED message.
  warn_settings_file — file_path=.claude/settings.json → exit 0 with WARNING.
  allow_normal_file  — file_path=src/app.py → exit 0 silent.
  empty_stdin        — no stdin → exit 0 silent (guard falls through).
  windows_path_token — C:\\-style file_path matching *.token → exit 2.
  path_field_fallback — tool_input.path (not .file_path) → exit 2 for a .key file.

The hook reads `guards.json` from its own script directory, so the .sh and
.py both pick up the checked-in default patterns without needing extra
fixture setup.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Dict, List

import pytest

from parity import Fixture, assert_parity  # type: ignore[import-not-found]


_REPO_ROOT = Path(__file__).resolve().parents[5]
_HOOK_SH = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "pre-tool-guard.sh"
_HOOK_PY = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "pre_tool_guard.py"
_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "pre_tool_guard"


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
