"""Pytest port of hooks/version-check.sh behavior (#609 / #572 Phase 3).

Covers the observable contract of the daily version-check hook:
  1. Cache hit for today with content → echo cached message, exit 0.
  2. Cache hit for today, empty → silent-pass.
  3. Malformed stdin → still consumed, silent-pass.
  4. Runs to completion inside a git-repo plugin (integration smoke test —
     no assertion on notice presence, only exit code, because the outcome
     depends on real HEAD vs origin/main).

The .sh (and this .py port) reads the cache from the hard-coded
`/tmp/adt-version-check-<today>` path — no `${TMPDIR:-/tmp}` fallback in
production. These tests never touch that real, shared path: each test
points the hook at its own `tmp_path`-scoped cache directory via
`DEV_TEAM_VERSION_CHECK_CACHE_DIR` (#1574) — worker/run-unique by
construction, since `tmp_path` is unique per test — so concurrent
pytest-xdist workers, or an entirely separate concurrent pytest process,
can never share or race on the file under test.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_HOOK_PY = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "version_check.py"

_HOOKS_DIR = _HOOK_PY.parent
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

import version_check  # type: ignore[import-not-found]


@pytest.fixture
def cache_file(tmp_path: Path) -> Path:
    """This test's own cache file, inside its own `tmp_path` cache dir."""
    # Must match version_check.py's own local-time `today` exactly (it
    # mirrors the ported .sh's `date +%Y-%m-%d`) or the cache path this
    # test reads/writes diverges from the one the hook under test uses.
    today = datetime.now().strftime("%Y-%m-%d")  # noqa: DTZ005
    return tmp_path / f"adt-version-check-{today}"


def _run(stdin: bytes = b"{}", *, cache_dir: Path) -> subprocess.CompletedProcess:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": "C.UTF-8",
        "HOME": os.environ.get("HOME", "/tmp"),
        "DEV_TEAM_VERSION_CHECK_CACHE_DIR": str(cache_dir),
    }
    return subprocess.run(
        [sys.executable, str(_HOOK_PY)],
        input=stdin,
        env=env,
        capture_output=True,
        timeout=15,
        check=False,
    )


def test_cache_hit_with_message_echoes_and_exits(cache_file: Path) -> None:
    cache_file.write_text("cached notice line\n")
    r = _run(cache_dir=cache_file.parent)
    assert r.returncode == 0
    assert r.stdout.decode() == "cached notice line\n"


def test_cache_hit_empty_is_silent_pass(cache_file: Path) -> None:
    cache_file.write_text("")
    r = _run(cache_dir=cache_file.parent)
    assert r.returncode == 0
    assert r.stdout == b""


def test_malformed_stdin_still_consumed(cache_file: Path) -> None:
    cache_file.write_text("")  # cache-short-circuit past network
    r = _run(stdin=b"{broken json ", cache_dir=cache_file.parent)
    assert r.returncode == 0
    assert r.stdout == b""


def test_stdin_variants_all_exit_0(cache_file: Path) -> None:
    cache_file.write_text("")
    for payload in (b"", b'{"malformed":', b'{"tool_name":"Read"}'):
        r = _run(stdin=payload, cache_dir=cache_file.parent)
        assert r.returncode == 0
        assert r.stdout == b""


def test_cache_replayed_line_normalization(cache_file: Path) -> None:
    """Bash's `CACHED=$(cat)` strips trailing newlines; `echo` adds exactly one
    back when non-empty. Verify the port matches byte-for-byte."""
    cache_file.write_text("notice\n\n\n")  # trailing whitespace
    r = _run(cache_dir=cache_file.parent)
    assert r.returncode == 0
    assert r.stdout == b"notice\n"


def test_cache_with_multi_line_message(cache_file: Path) -> None:
    """A multi-line cache is echoed with each line preserved (bash `echo` on
    a multi-line variable emits the whole thing plus one trailing LF)."""
    cache_file.write_text("line1\nline2")
    r = _run(cache_dir=cache_file.parent)
    assert r.returncode == 0
    assert r.stdout == b"line1\nline2\n"


def test_cache_dir_falls_back_to_real_tmp_when_override_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every other test in this file always sets DEV_TEAM_VERSION_CHECK_CACHE_DIR
    (#1574) to avoid the real, shared /tmp path — which means the actual
    production default (what every real user hits) went untested as a side
    effect. Pin it directly, without touching the real cache file."""
    monkeypatch.delenv("DEV_TEAM_VERSION_CHECK_CACHE_DIR", raising=False)
    assert version_check._cache_dir() == Path("/tmp")
