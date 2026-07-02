"""Parity fixtures for hooks/token-efficiency-review (#607 / #572 Phase 3).

The hook reads a file whose path lives in the JSON payload; fixture files
under `initial_tree/` are placed in the sandbox root. The stdin payload
uses the literal path token `SANDBOX` which the harness substitutes with
the actual sandbox root at dispatch time.

Wait — dispatch() only substitutes SANDBOX in argv, not stdin. So we
generate the payload dynamically here: read `path_in_sandbox` from
`meta.json` and rewrite the stdin.

Fixture layout (per subdirectory of fixtures/token_efficiency_review/):
    meta.json               - {"path_in_sandbox": "<relative path>"}
                              — the file the hook should inspect
    initial_tree/           - files copied into the sandbox root before run
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import pytest

from parity import Fixture, assert_parity, dispatch  # type: ignore[import-not-found]


_REPO_ROOT = Path(__file__).resolve().parents[5]
_HOOK_SH = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "token-efficiency-review.sh"
_HOOK_PY = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "token_efficiency_review.py"
_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "token_efficiency_review"


def _load_fixture(dirpath: Path) -> tuple:
    meta_path = dirpath / "meta.json"
    meta: Dict[str, str] = (
        json.loads(meta_path.read_text()) if meta_path.is_file() else {}
    )
    initial_tree: Dict[str, str] = {}
    tree_root = dirpath / "initial_tree"
    if tree_root.is_dir():
        for path in tree_root.rglob("*"):
            if path.is_file():
                rel = str(path.relative_to(tree_root))
                initial_tree[rel] = path.read_text()
    return meta, initial_tree


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
    import shutil

    if shutil.which("jq") is None:
        pytest.skip("jq required by the .sh")
    meta, initial_tree = _load_fixture(fixture_dir)
    path_in_sandbox = meta.get("path_in_sandbox", "")
    # Build one dispatch per side so we can rewrite SANDBOX after the harness
    # gives us a tmpdir. We invoke dispatch() twice — once per side — with a
    # rebuilt stdin that names the actual sandbox path.
    #
    # This is what assert_parity does; we duplicate it because we need to
    # rewrite the payload with the tmp path per-side.

    def _run_side(hook_cmd: List[str]):
        # dispatch() creates a fresh sandbox internally and returns its path.
        # We can't inject the path pre-dispatch, so build a fixture with an
        # empty stdin (the hook silent-passes), then the harness returns the
        # sandbox root — no help. Instead: point at a path constructed with
        # `SANDBOX` inside the payload; the .sh reads
        # `.tool_input.file_path`, and inside the subprocess CWD == sandbox
        # root. Use a RELATIVE path in the payload — both implementations
        # `[ -f "$FILE_PATH" ]`/`Path.is_file()` resolve relative to CWD.
        payload = json.dumps({"tool_input": {"file_path": path_in_sandbox}}).encode()
        return dispatch(
            hook_cmd,
            stdin_bytes=payload,
            initial_tree=initial_tree,
        )

    sh_result = _run_side(["bash", str(_HOOK_SH)])
    py_result = _run_side(["python3", str(_HOOK_PY)])
    assert sh_result.exit_code == py_result.exit_code, (
        f"[{fixture_dir.name}] exit code diverged"
    )
    assert sh_result.stdout == py_result.stdout, (
        f"[{fixture_dir.name}] stdout diverged\n"
        f"sh: {sh_result.stdout!r}\npy: {py_result.stdout!r}"
    )
    assert sh_result.stderr == py_result.stderr, f"[{fixture_dir.name}] stderr diverged"
    assert sh_result.tree == py_result.tree, f"[{fixture_dir.name}] tree diverged"
