"""Unit tests for hooks/lib/atomic_state.py, focused on the #1889 security
hardening of `locked_state`'s lock-file open (symlink-follow, permissions)
and `race_window_delay`'s cap.

Neither control was previously pinned by a test — both were verified only
by a manual, unrecorded run — so a regression (reverting to a bare
`open(lock_path, "a+")`, or dropping the delay cap) could land with the
whole suite green.
"""

from __future__ import annotations

import os
import stat
import sys
import time
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parents[2] / "hooks" / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import atomic_state  # type: ignore[import-not-found]
import pytest


def test_locked_state_does_not_follow_a_symlinked_lock_file(tmp_path: Path) -> None:
    if not hasattr(os, "O_NOFOLLOW"):
        pytest.skip("platform has no O_NOFOLLOW")
    target = tmp_path / "outside-target.txt"
    log = tmp_path / "log.jsonl"
    lock_path = tmp_path / "log.jsonl.lock"
    os.symlink(str(target), str(lock_path))

    with atomic_state.locked_state(log):
        pass

    assert not target.exists(), "symlinked lock file must not be followed"
    assert os.path.islink(lock_path), "the planted symlink itself must be left untouched"


def test_locked_state_creates_lock_file_at_mode_0600(tmp_path: Path) -> None:
    if os.name != "posix":
        pytest.skip("POSIX file mode semantics only")
    log = tmp_path / "log.jsonl"

    with atomic_state.locked_state(log):
        pass

    lock_path = tmp_path / "log.jsonl.lock"
    mode = stat.S_IMODE(lock_path.stat().st_mode)
    assert mode == 0o600


def test_locked_state_fixes_mode_on_a_pre_existing_lock_file(tmp_path: Path) -> None:
    """A lock file created by the pre-#1889 code (bare `open(..., "a+")`, no
    explicit mode) sits at the umask default — typically 0644. `os.open`'s
    mode argument is ignored for a path that already exists, so this only
    passes because of the added `os.fchmod` call."""
    if os.name != "posix":
        pytest.skip("POSIX file mode semantics only")
    log = tmp_path / "log.jsonl"
    lock_path = tmp_path / "log.jsonl.lock"
    lock_path.touch(mode=0o644)
    os.chmod(lock_path, 0o644)

    with atomic_state.locked_state(log):
        pass

    mode = stat.S_IMODE(lock_path.stat().st_mode)
    assert mode == 0o600


def test_append_line_locked_does_not_follow_a_symlinked_data_file(tmp_path: Path) -> None:
    if not hasattr(os, "O_NOFOLLOW"):
        pytest.skip("platform has no O_NOFOLLOW")
    target = tmp_path / "outside-target.txt"
    log = tmp_path / "log.jsonl"
    os.symlink(str(target), str(log))

    atomic_state.append_line_locked(log, "line\n")

    assert not target.exists(), "symlinked data file must not be followed"
    assert os.path.islink(log), "the planted symlink itself must be left untouched"


def test_race_window_delay_caps_a_large_value(monkeypatch) -> None:
    monkeypatch.setenv("TEST_DELAY_MS", "10000000")
    start = time.monotonic()
    atomic_state.race_window_delay("TEST_DELAY_MS")
    elapsed = time.monotonic() - start
    assert elapsed < 2.0, f"race_window_delay did not cap, took {elapsed}s"


def test_race_window_delay_negative_value_is_a_noop(monkeypatch) -> None:
    monkeypatch.setenv("TEST_DELAY_MS", "-5")
    start = time.monotonic()
    atomic_state.race_window_delay("TEST_DELAY_MS")
    elapsed = time.monotonic() - start
    assert elapsed < 1.0
