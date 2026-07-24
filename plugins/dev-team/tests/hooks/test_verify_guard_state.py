"""Unit tests for hooks/lib/verify_guard_state.py (#708).

White-box coverage of the shared state-key/read/write helpers used by
both verify_guard.py and verify_guard_edit_marker.py — subprocess-level
integration coverage of those two hooks lives in
tests/hooks/test_verify_guard.py at the repo root.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

_HOOKS_LIB = Path(__file__).resolve().parents[2] / "hooks" / "lib"
if str(_HOOKS_LIB) not in sys.path:
    sys.path.insert(0, str(_HOOKS_LIB))

import verify_guard_state as vgs  # type: ignore[import-not-found]


def test_state_key_prefers_session_id() -> None:
    assert vgs.state_key("abc-123", "/some/cwd") == "abc-123"


def test_state_key_falls_back_to_cksum_of_cwd() -> None:
    key = vgs.state_key("", "/some/cwd")
    assert key != ""
    assert key == vgs.cksum("/some/cwd")


def test_state_file_lives_under_shared_dirname(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    path = vgs.state_file("session-x")
    assert path == tmp_path / "dev-team-verify-guard" / "session-x.json"


def test_write_then_read_state_roundtrips(tmp_path: Path) -> None:
    path = tmp_path / "dev-team-verify-guard" / "s.json"
    vgs.write_state(path, {"hash": "abc", "count": 2, "edited": True})
    data = vgs.read_state(path)
    assert data == {"hash": "abc", "count": 2, "edited": True}


def test_read_state_missing_file_returns_empty_dict(tmp_path: Path) -> None:
    assert vgs.read_state(tmp_path / "nope.json") == {}


def test_read_state_malformed_json_returns_empty_dict(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not json")
    assert vgs.read_state(path) == {}


def test_cksum_deterministic_for_same_input() -> None:
    assert vgs.cksum("npm test") == vgs.cksum("npm test")
    assert vgs.cksum("npm test") != vgs.cksum("pytest -q")


def test_cksum_does_not_shell_out_to_external_binary(monkeypatch) -> None:
    """Regression guard (Low-severity finding): `cksum` used to shell out to
    the external `cksum` binary per call, a bash-parity leftover no longer
    needed now that the .sh implementations are gone. It must hash
    in-process instead, matching bash_retry_guard.py's own approach."""
    import subprocess

    def _boom(*args, **kwargs):  # pragma: no cover - only runs if regressed
        raise AssertionError("cksum() must not shell out to a subprocess")

    monkeypatch.setattr(subprocess, "run", _boom)
    assert vgs.cksum("npm test") == vgs.cksum("npm test")


def test_cksum_matches_bash_retry_guard_algorithm() -> None:
    """Same algorithm as bash_retry_guard.py's `_cksum` (zlib.crc32) so
    checksums stay comparable if anything ever persists/compares both."""
    _HOOKS_DIR = Path(__file__).resolve().parents[2] / "hooks"
    if str(_HOOKS_DIR) not in sys.path:
        sys.path.insert(0, str(_HOOKS_DIR))
    import bash_retry_guard  # type: ignore[import-not-found]

    for text in ["npm test", "pytest -q", "", "weird\tinput\nwith  spaces"]:
        assert vgs.cksum(text) == bash_retry_guard._cksum(text)


# ---------------------------------------------------------------------------
# purge_stale — TTL purge on write (#732)
#
# verify_guard.py / verify_guard_edit_marker.py each write one state file per
# session with no expiry, unlike tdd_guard.py / mutation_adapters/lib.py's
# `_purge_stale`. Both hooks write through `write_state`, so the purge lives
# there as the single choke point.
# ---------------------------------------------------------------------------


def test_purge_stale_removes_old_files_but_keeps_fresh(tmp_path: Path) -> None:
    state_dir = tmp_path / "dev-team-verify-guard"
    state_dir.mkdir(parents=True)

    stale = state_dir / "old-session.json"
    stale.write_text("{}")
    old_time = time.time() - vgs._STATE_TTL_SECONDS - 60
    os.utime(stale, (old_time, old_time))

    fresh = state_dir / "recent-session.json"
    fresh.write_text("{}")

    vgs.purge_stale(state_dir)

    assert not stale.exists()
    assert fresh.exists()


def test_write_state_purges_stale_sibling_state_files(tmp_path: Path) -> None:
    """The TTL purge fires on every write_state call, not just on request."""
    state_dir = tmp_path / "dev-team-verify-guard"
    state_dir.mkdir(parents=True)

    stale = state_dir / "old-session.json"
    stale.write_text('{"hash":"x","count":1}')
    old_time = time.time() - vgs._STATE_TTL_SECONDS - 60
    os.utime(stale, (old_time, old_time))

    vgs.write_state(state_dir / "new-session.json", {"hash": "y", "count": 1})

    assert not stale.exists()
    assert (state_dir / "new-session.json").exists()
