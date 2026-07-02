"""Parity fixtures for hooks/session-learning-trigger (#603).

Six fixtures spanning the consent-off pathway and the consent-on counter-
increment pathway (with corrupt-state recovery). The **dispatch** pathway
(threshold reached → background analysis) is deliberately excluded — both
implementations fork a detached child and the harness cannot observe that
side effect within the sandbox lifetime.

Layout:
  consent_off_default             — auto-review not enabled, exit 0 silent.
  consent_off_malformed_stdin     — invalid JSON, still exit 0.
  consent_off_empty_stdin         — empty body, still exit 0.
  consent_on_counter_increment    — threshold=5, no prior state → counter=1.
  consent_on_corrupt_state_recovers — corrupt state file → counter recovers to 1.
  windows_path_cwd_no_dispatch    — Windows-style cwd (nonexistent), falls
                                    back to $PWD (the sandbox) and counter=0.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Dict, List

import pytest

from parity import Fixture, assert_parity  # type: ignore[import-not-found]


_REPO_ROOT = Path(__file__).resolve().parents[5]
_HOOK_SH = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "session-learning-trigger.sh"
_HOOK_PY = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "session_learning_trigger.py"
_FIXTURES_DIR = (
    Path(__file__).resolve().parent / "fixtures" / "session_learning_trigger"
)


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
