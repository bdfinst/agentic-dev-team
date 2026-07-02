"""Parity fixtures for hooks/codegraph_nudge (#593).

The nudge hook writes only to stderr; stdout is always empty. Careful-mode
and sentinel tests are covered by the per-hook unit tests — the parity
fixtures exercise the observable branches (silent no-op, warn to stderr,
malformed input silent).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Dict, List

import pytest

from parity import Fixture, dispatch, _normalize_stderr  # type: ignore[import-not-found]


_REPO_ROOT = Path(__file__).resolve().parents[5]
_HOOK_SH = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "codegraph-nudge.sh"
_HOOK_PY = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "codegraph_nudge.py"
_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "codegraph_nudge"


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
def test_codegraph_nudge_parity(fixture_dir: Path) -> None:
    if shutil.which("jq") is None:
        pytest.skip("jq required by the .sh")
    fixture = _load_fixture(fixture_dir)
    # For fixtures that set up a .codegraph/ inside the sandbox, the payload
    # must reference the sandbox path. Since dispatch() sets CWD to the
    # sandbox, we rewrite payload cwd (or omit it) so both sides resolve to
    # the sandbox root.
    if fixture.stdin.startswith(b"{"):
        try:
            payload = json.loads(fixture.stdin.decode("utf-8"))
            if isinstance(payload, dict):
                payload.pop("cwd", None)
                new_stdin = json.dumps(payload, separators=(",", ":")).encode("utf-8")
                fixture = Fixture(
                    name=fixture.name,
                    stdin=new_stdin,
                    argv=fixture.argv,
                    env=fixture.env,
                    initial_tree=fixture.initial_tree,
                )
        except json.JSONDecodeError:
            pass
    sh = dispatch(
        ["bash", str(_HOOK_SH)],
        stdin_bytes=fixture.stdin,
        env=fixture.env,
        initial_tree=fixture.initial_tree,
    )
    py = dispatch(
        ["python3", str(_HOOK_PY)],
        stdin_bytes=fixture.stdin,
        env=fixture.env,
        initial_tree=fixture.initial_tree,
    )
    assert sh.exit_code == py.exit_code, (
        f"[{fixture.name}] exit sh={sh.exit_code} py={py.exit_code}"
    )
    assert sh.stdout == py.stdout == b"", (
        f"[{fixture.name}] stdout sh={sh.stdout!r} py={py.stdout!r}"
    )
    sh_err = _normalize_stderr(sh.stderr, sh.sandbox_root)
    py_err = _normalize_stderr(py.stderr, py.sandbox_root)
    assert sh_err == py_err, (
        f"[{fixture.name}] stderr diverged\nsh: {sh_err!r}\npy: {py_err!r}"
    )
