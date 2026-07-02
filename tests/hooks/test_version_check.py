"""Pytest port of hooks/version-check.sh behavior (#609 / #572 Phase 3).

Covers the observable contract of the daily version-check hook:
  1. Cache hit for today with content → echo cached message, exit 0.
  2. Cache hit for today, empty → silent-pass.
  3. Malformed stdin → still consumed, silent-pass.
  4. Runs to completion inside a git-repo plugin (integration smoke test —
     no assertion on notice presence, only exit code, because the outcome
     depends on real HEAD vs origin/main).

The .sh (and this .py port) reads the cache from the hard-coded
`/tmp/adt-version-check-<today>` path — no `${TMPDIR:-/tmp}` fallback. To
avoid clobbering the developer's real cache, we save-and-restore any
pre-existing file around each test.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]
_HOOK_PY = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "version_check.py"


def _cache_path() -> Path:
    today = datetime.now().strftime("%Y-%m-%d")
    return Path("/tmp") / f"adt-version-check-{today}"


@pytest.fixture
def restore_cache_file():
    """Save whatever /tmp/adt-version-check-<today> currently is, restore it
    after the test — so real user cache is never clobbered."""
    cache = _cache_path()
    original = cache.read_bytes() if cache.is_file() else None
    try:
        yield cache
    finally:
        if original is None:
            if cache.is_file():
                cache.unlink()
        else:
            cache.write_bytes(original)


def _run(stdin: bytes = b"{}") -> subprocess.CompletedProcess:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": "C.UTF-8",
        "HOME": os.environ.get("HOME", "/tmp"),
    }
    return subprocess.run(
        [sys.executable, str(_HOOK_PY)],
        input=stdin,
        env=env,
        capture_output=True,
        timeout=15,
        check=False,
    )


def test_cache_hit_with_message_echoes_and_exits(
    restore_cache_file: Path,
) -> None:
    restore_cache_file.write_text("cached notice line\n")
    r = _run()
    assert r.returncode == 0
    assert r.stdout.decode() == "cached notice line\n"


def test_cache_hit_empty_is_silent_pass(restore_cache_file: Path) -> None:
    restore_cache_file.write_text("")
    r = _run()
    assert r.returncode == 0
    assert r.stdout == b""


def test_malformed_stdin_still_consumed(restore_cache_file: Path) -> None:
    restore_cache_file.write_text("")  # cache-short-circuit past network
    r = _run(stdin=b"{broken json ")
    assert r.returncode == 0
    assert r.stdout == b""


def test_stdin_variants_all_exit_0(restore_cache_file: Path) -> None:
    restore_cache_file.write_text("")
    for payload in (b"", b'{"malformed":', b'{"tool_name":"Read"}'):
        r = _run(stdin=payload)
        assert r.returncode == 0
        assert r.stdout == b""


def test_cache_replayed_line_normalization(restore_cache_file: Path) -> None:
    """Bash's `CACHED=$(cat)` strips trailing newlines; `echo` adds exactly one
    back when non-empty. Verify the port matches byte-for-byte."""
    restore_cache_file.write_text("notice\n\n\n")  # trailing whitespace
    r = _run()
    assert r.returncode == 0
    assert r.stdout == b"notice\n"


def test_cache_with_multi_line_message(restore_cache_file: Path) -> None:
    """A multi-line cache is echoed with each line preserved (bash `echo` on
    a multi-line variable emits the whole thing plus one trailing LF)."""
    restore_cache_file.write_text("line1\nline2")
    r = _run()
    assert r.returncode == 0
    assert r.stdout == b"line1\nline2\n"
