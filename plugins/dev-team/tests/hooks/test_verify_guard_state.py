"""Unit tests for hooks/lib/verify_guard_state.py (#708).

White-box coverage of the shared state-key/read/write helpers used by
both verify_guard.py and verify_guard_edit_marker.py — subprocess-level
integration coverage of those two hooks lives in
tests/hooks/test_verify_guard.py at the repo root.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_HOOKS_LIB = Path(__file__).resolve().parents[2] / "hooks" / "lib"
if str(_HOOKS_LIB) not in sys.path:
    sys.path.insert(0, str(_HOOKS_LIB))

import verify_guard_state as vgs  # type: ignore[import-not-found]  # noqa: E402


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
