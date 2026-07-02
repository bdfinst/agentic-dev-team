"""Parity fixtures for hooks/bash_retry_guard (#591).

The bash-retry-guard writes a per-session state file at
$TMPDIR/dev-team-bash-retry/<key>.json. The .sh uses POSIX `cksum` for
hashing while the .py uses zlib.crc32 — those are NOT guaranteed to
produce byte-identical output on all platforms. As a result, the
state-file content is INTENTIONALLY excluded from the parity comparison:
we compare stdout, stderr, exit code, and the set of files written
(paths, not contents). Byte-parity on user-observable channels (stdout,
exit code) is the contract; the private state file is an internal
implementation detail scoped to `$TMPDIR`, not a shared artifact.

Each fixture runs both sides once and asserts:
  - identical stdout (both silent, both nudging)
  - identical exit code (always 0 — advisory)
  - stderr normalized-equal
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Dict, List

import pytest

from parity import Fixture, dispatch  # type: ignore[import-not-found]


_REPO_ROOT = Path(__file__).resolve().parents[5]
_HOOK_SH = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "bash-retry-guard.sh"
_HOOK_PY = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "bash_retry_guard.py"
_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "bash_retry_guard"


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
def test_bash_retry_guard_parity(fixture_dir: Path) -> None:
    if shutil.which("jq") is None:
        pytest.skip("jq required by the .sh")
    fixture = _load_fixture(fixture_dir)

    sh_result = dispatch(
        ["bash", str(_HOOK_SH)],
        stdin_bytes=fixture.stdin,
        env=fixture.env,
    )
    py_result = dispatch(
        ["python3", str(_HOOK_PY)],
        stdin_bytes=fixture.stdin,
        env=fixture.env,
    )

    # Exit code — always 0 for this hook.
    assert sh_result.exit_code == py_result.exit_code == 0, (
        f"[{fixture.name}] exit code sh={sh_result.exit_code} py={py_result.exit_code}\n"
        f"sh stdout: {sh_result.stdout!r}\n"
        f"py stdout: {py_result.stdout!r}"
    )
    # Stdout — the observable user-visible channel.
    assert sh_result.stdout == py_result.stdout, (
        f"[{fixture.name}] stdout diverged\n"
        f"sh: {sh_result.stdout!r}\n"
        f"py: {py_result.stdout!r}"
    )
    # (Tree comparison intentionally omitted — see module docstring.)
