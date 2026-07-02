"""Parity fixtures for hooks/mutation-testing-smoke-gate (#574).

Runs the .sh and .py implementations against six fixtures covering the
hook's full observable surface. assert_parity fails the merge on any
byte-level divergence in stdout, exit code, normalized stderr, or
side-effect tree.

Fixture layout (per subdirectory of fixtures/mutation_testing_smoke_gate/):
    stdin.json              - stdin payload for the hook (required)
    env.json                - {name: value} env overlay (optional)
    initial_tree/           - files copied into the sandbox root before run
                              (optional; the smoke-report fixtures use this)
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Dict, List

import pytest

from parity import Fixture, assert_parity  # type: ignore[import-not-found]


_REPO_ROOT = Path(__file__).resolve().parents[5]
_HOOK_SH = (
    _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "mutation-testing-smoke-gate.sh"
)
_HOOK_PY = (
    _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "mutation_testing_smoke_gate.py"
)
_FIXTURES_DIR = (
    Path(__file__).resolve().parent / "fixtures" / "mutation_testing_smoke_gate"
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
    # Both implementations reference their smoke report via <cwd>/StrykerOutput/...
    # The stdin.json's `cwd` field must point at SANDBOX for tree seeding to work;
    # we substitute the sandbox root string in the payload before dispatch.
    # Simpler: fixtures set "cwd" to the string "SANDBOX" in stdin.json; we
    # rewrite it here for both sides.
    if b"SANDBOX" in fixture.stdin:
        # dispatch() creates a fresh sandbox per side; we can't pre-know it.
        # Instead: the hook's default cwd fallback is $PWD when cwd is missing.
        # Rewrite "cwd": "SANDBOX" → drop the key so both sides fall back to
        # subprocess cwd (the sandbox root). This keeps stdin byte-identical
        # between sides.
        payload = json.loads(fixture.stdin.decode("utf-8"))
        payload.pop("cwd", None)
        fixture = Fixture(
            name=fixture.name,
            stdin=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            argv=fixture.argv,
            env=fixture.env,
            initial_tree=fixture.initial_tree,
        )
    assert_parity(
        sh_argv=["bash", str(_HOOK_SH)],
        py_argv=["python3", str(_HOOK_PY)],
        fixture=fixture,
    )
