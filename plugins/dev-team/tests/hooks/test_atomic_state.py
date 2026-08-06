"""Unit tests for hooks/lib/atomic_state.py, focused on the #1889 security
hardening of `locked_state`'s lock-file open (symlink-follow, permissions)
and `race_window_delay`'s cap.

Neither control was previously pinned by a test — both were verified only
by a manual, unrecorded run — so a regression (reverting to a bare
`open(lock_path, "a+")`, or dropping the delay cap) could land with the
whole suite green.
"""

from __future__ import annotations

import errno
import os
import stat
import sys
import threading
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


def test_locked_state_propagates_a_caller_raised_oserror(tmp_path: Path) -> None:
    """#1892: a caller whose `with locked_state(path):` body raises OSError
    must see that exact OSError propagate — not
    `RuntimeError("generator didn't stop after throw()")`. The prior
    implementation's outer `except OSError` wrapped the whole `with
    os.fdopen(...)` block, including the `yield` where the caller's code
    runs, so a caller-raised OSError fell into that same handler and the
    generator went on to hit a second bare `yield`."""
    log = tmp_path / "log.jsonl"

    with pytest.raises(OSError, match="boom"), atomic_state.locked_state(log):
        raise OSError("boom")


def test_locked_state_still_fails_open_when_fdopen_itself_fails(
    tmp_path: Path, monkeypatch
) -> None:
    """The fdopen()-failure fail-open path (parent dir or lock file itself
    can't be opened) must still fall through to running the critical
    section unlocked, unchanged by the #1892 fix."""
    log = tmp_path / "log.jsonl"
    ran_unlocked = False

    def _boom(*_args, **_kwargs):
        raise OSError("fdopen failed")

    monkeypatch.setattr(atomic_state.os, "fdopen", _boom)

    with atomic_state.locked_state(log):
        ran_unlocked = True

    assert ran_unlocked, "critical section must still run when fdopen() fails"


def test_locked_state_fdopen_failure_prints_a_stderr_diagnostic(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """#1904 item 6: a fail-open fallthrough must never be silent. This pins
    the fdopen()-failure path (the easiest of the four fail-open paths to
    trigger deterministically) — the other three (parent-mkdir failure,
    lock-file-open failure, budget exhaustion) emit the analogous diagnostic
    at their own fallthrough point in `locked_state`."""
    log = tmp_path / "log.jsonl"

    def _boom(*_args, **_kwargs):
        raise OSError("fdopen failed")

    monkeypatch.setattr(atomic_state.os, "fdopen", _boom)

    with atomic_state.locked_state(log):
        pass

    captured = capsys.readouterr()
    assert "atomic_state: lock acquisition failed" in captured.err
    assert "proceeding WITHOUT lock" in captured.err
    assert str(log) in captured.err


def test_lock_contention_errnos_includes_deadlock_errnos_when_present() -> None:
    """#1904 item 9: Windows CRT `_locking` may surface a deadlock-shaped
    errno on contention; treating that as a non-retryable error would give
    up the lock immediately instead of retrying, indistinguishable from a
    genuine failure. Defensive on platforms where these attributes exist at
    all — `getattr(..., None)` already filters an absent platform out."""
    for name in ("EDEADLOCK", "EDEADLK"):
        code = getattr(errno, name, None)
        if code is not None:
            assert code in atomic_state._LOCK_CONTENTION_ERRNOS


# ---------------------------------------------------------------------------
# strict mode (issue #1920 Step 1.1): a caller that must never silently run
# unlocked opts in with `strict=True` — the same four fail-open fallback
# points raise RuntimeError instead of printing + running unlocked.
# ---------------------------------------------------------------------------


def test_locked_state_strict_true_runs_critical_section_when_lock_acquired(
    tmp_path: Path,
) -> None:
    """(a) `strict=True` with a lock successfully acquired behaves exactly
    like `strict=False`: the critical section runs, under the lock, with no
    exception raised."""
    log = tmp_path / "log.jsonl"
    ran = False

    with atomic_state.locked_state(log, strict=True):
        ran = True

    assert ran, "critical section must run when the lock is acquired, strict or not"


def test_locked_state_strict_true_raises_when_acquire_budget_exhausts(
    tmp_path: Path, monkeypatch
) -> None:
    """(b) `strict=True` against a held competing lock, with the acquire
    budget forced to exhaust (`DEV_TEAM_LOCK_ACQUIRE_BUDGET_TEST_MS`, the
    same test-only override `test_locked_state_gives_up_after_stalled_holder`
    in `test_hook_state_concurrency.py` uses), must raise `RuntimeError`
    instead of silently running the critical section unlocked."""
    state_file = tmp_path / "counter.json"
    state_file.write_text("{}")

    hold_seconds = 0.4
    budget_ms = 50
    acquired = threading.Event()

    def _hold_lock():
        with atomic_state.locked_state(state_file):
            acquired.set()
            time.sleep(hold_seconds)

    holder = threading.Thread(target=_hold_lock)
    holder.start()
    ran_unlocked = False
    try:
        assert acquired.wait(timeout=2), "holder thread never acquired the lock"

        monkeypatch.setenv("DEV_TEAM_LOCK_ACQUIRE_BUDGET_TEST_MS", str(budget_ms))
        with (
            pytest.raises(RuntimeError, match="budget exhausted"),
            atomic_state.locked_state(state_file, strict=True),
        ):
            ran_unlocked = True
    finally:
        holder.join(timeout=2)
    assert not holder.is_alive(), "holder thread never released the lock"
    assert not ran_unlocked, (
        "strict=True must never run the critical section when the lock "
        "could not be acquired"
    )


def test_locked_state_strict_true_raises_when_fdopen_fails(
    tmp_path: Path, monkeypatch
) -> None:
    """Covers the fdopen()-failure fail-open point specifically: strict=True
    raises RuntimeError instead of the fail-open fallthrough exercised by
    `test_locked_state_still_fails_open_when_fdopen_itself_fails` above."""
    log = tmp_path / "log.jsonl"
    ran_unlocked = False

    def _boom(*_args, **_kwargs):
        raise OSError("fdopen failed")

    monkeypatch.setattr(atomic_state.os, "fdopen", _boom)

    with (
        pytest.raises(RuntimeError, match="fdopen"),
        atomic_state.locked_state(log, strict=True),
    ):
        ran_unlocked = True

    assert not ran_unlocked, (
        "strict=True must never run the critical section when fdopen() fails"
    )


def test_locked_state_strict_false_behavior_is_unchanged(
    tmp_path: Path, monkeypatch
) -> None:
    """(c) `strict=False` (the default, omitted entirely here — matching
    every pre-existing caller's call shape) still fails open on the same
    fdopen() failure rather than raising, proving the default path is
    untouched by the strict-mode addition."""
    log = tmp_path / "log.jsonl"
    ran_unlocked = False

    def _boom(*_args, **_kwargs):
        raise OSError("fdopen failed")

    monkeypatch.setattr(atomic_state.os, "fdopen", _boom)

    with atomic_state.locked_state(log):
        ran_unlocked = True

    assert ran_unlocked, "strict=False (default) must keep failing open"
