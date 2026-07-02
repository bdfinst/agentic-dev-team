"""Parity fixtures for hooks/mutation-gate (#588 / #572 Phase 2 D1).

Six fixtures span the fast-path branches the hook itself dispatches — the
paths that never reach the per-adapter modules. The adapter-invocation paths
(stryker/pitest/etc. running real mutation tools) are covered by the
Cluster D unit tests in `tests/hooks/test_mutation_adapters_lib.py` and by
manual smoke runs in real projects; the parity harness does NOT reproduce
the mutation-tool subprocess trees because they take minutes and touch the
real filesystem.

  empty_stdin_silent               — empty body → exit 0 silent.
  malformed_stdin_silent           — invalid JSON → exit 0 silent.
  non_test_command_silent          — `npm run build` → is_test_command false.
  skip_env_silent                  — MUTATION_GATE_SKIP=1 → exit 0 silent.
  red_first_touch_no_transition    — failing test with no prior state → no
                                     RED→GREEN transition → exit 0 silent
                                     (state file gets written, and hashes
                                     match because the state format is jq-
                                     parity across implementations).
  windows_command_silent           — Windows batch path → is_test_command
                                     false → exit 0 silent.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Dict, List

import pytest

from parity import Fixture, assert_parity  # type: ignore[import-not-found]


_REPO_ROOT = Path(__file__).resolve().parents[5]
_HOOK_SH = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "mutation-gate.sh"
_HOOK_PY = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "mutation_gate.py"
_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "mutation_gate"


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
