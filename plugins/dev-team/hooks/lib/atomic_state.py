"""atomic_state — shared atomic-write + cross-OS advisory-lock helpers for hooks.

Several advisory hooks persist tiny per-session/per-project state with a
read-modify-write cycle against a shared on-disk file. Two concurrent
invocations (two Bash tool calls firing close together, or two
sessions/worktrees touching the same repo) can race and lose an update
(#1501). This module centralizes the two primitives that close that race:

- `atomic_write(path, text)` — write via a same-directory tempfile + rename
  so a concurrent reader never observes a torn/partial file.
- `locked_state(path)` — a cross-OS exclusive advisory lock held for the
  full read-modify-write cycle so counters increment exactly once per
  invocation instead of clobbering each other.

The lock idiom (`fcntl.flock` on POSIX, `msvcrt.locking` on Windows,
fail-open when neither is available) is lifted from the already-proven copy
in `hooks/code_intelligence_turn_mark.py::_sentinel_lock` so the two agree
on behavior. Everything here is fail-open: any I/O or locking failure runs
the critical section unlocked / skips the persist rather than raising —
these are advisory nudges, never gates.

Stdlib-only.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path

try:
    import fcntl  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover — Windows has no fcntl
    fcntl = None  # type: ignore[assignment]

try:
    import msvcrt  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover — POSIX has no msvcrt
    msvcrt = None  # type: ignore[assignment]


def atomic_write(path: Path, text: str) -> None:
    """Write `text` to `path` atomically via tempfile-in-same-dir + rename.

    A concurrent reader sees either the old file or the fully-written new one,
    never a partial write. Fail-open: any OSError short-circuits to a silent
    no-op — persistence is best-effort for these advisory hooks.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    try:
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{path.name}-", suffix=".tmp", dir=str(path.parent)
        )
    except OSError:
        return
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_name, path)
    except OSError:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)


@contextlib.contextmanager
def locked_state(path: Path) -> Iterator[None]:
    """Hold an exclusive advisory lock for a full read-modify-write cycle.

    Prevents the lost-update race where two concurrent invocations both read
    the same stale value, both increment it, and one write clobbers the
    other. `fcntl.flock` on POSIX, `msvcrt.locking` on Windows (this repo's
    hooks target both — ADR 0014/0015). The lock file lives beside `path` as
    `<path>.lock`.

    Fail-open: a missing `fcntl` *and* `msvcrt`, or any OSError opening/locking
    the lock file, falls through to running the critical section UNLOCKED
    rather than raising. An unlocked lost-update is no worse than the
    pre-#1501 behavior; a crash would be worse, and these hooks are advisory.
    """
    lock_path = path.parent / (path.name + ".lock")
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        yield
        return

    # The open() failure case shares this try/except with the whole `with`
    # body (ruff SIM115 requires open() directly in a `with`). Callers own
    # their own OSError handling inside the critical section, so this outer
    # except only ever fires for the open() call itself.
    try:
        with open(lock_path, "a+") as handle:
            locked = False
            try:
                try:
                    if fcntl is not None:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                        locked = True
                    elif msvcrt is not None:
                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                        locked = True
                except OSError:
                    locked = False
                yield
            finally:
                if locked:
                    try:
                        if fcntl is not None:
                            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                        elif msvcrt is not None:
                            handle.seek(0)
                            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    except OSError:
                        pass
            return
    except OSError:
        pass
    yield


def race_window_delay(env_var: str) -> None:
    """Test-only injection point: sleep inside a locked critical section when
    `env_var` names a millisecond delay, widening the race window so a
    concurrency test can deterministically force two invocations to overlap
    rather than relying on timing luck. Unset in production; a bad/missing
    value is a no-op (fail-open). Mirrors
    `code_intelligence_turn_mark._test_delay`.
    """
    raw = os.environ.get(env_var)
    if not raw:
        return
    try:
        time.sleep(int(raw) / 1000)
    except (ValueError, OSError):
        pass
