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
fail-open when neither is available) started as a copy of
`hooks/code_intelligence_turn_mark.py::_sentinel_lock` — #1888 (below) bounded
the acquire wait here but deliberately left that sibling's blocking wait
alone (a PostToolUse nudge sentinel, not a safety-critical guard verdict), so
the two no longer agree on acquire behavior; only the release-path idiom
still matches. Everything here is fail-open: any I/O or locking failure runs
the critical section unlocked / skips the persist rather than raising —
these are advisory nudges, never gates.

Lock *acquisition* is bounded, not a blocking wait (#1888): a hung sibling
process holding the lock must never leave a caller blocked indefinitely,
since some callers (e.g. `boundary_events.py`, once #1874 lands) sit in
front of a safety-critical guard hook's verdict. `locked_state` polls a
non-blocking acquisition for a bounded total budget and falls through to
running the critical section UNLOCKED once that budget elapses — the same
fail-open posture as every other failure mode here. This bounds contention
on an already-held lock specifically; it does NOT bound a stall inside
`open()` on the lock file itself, or inside a caller's own I/O in the
critical section — a wedged mount can still block there.

Stdlib-only.
"""

from __future__ import annotations

import contextlib
import errno
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


# Total time `locked_state` will poll for the lock before giving up and
# running the critical section unlocked (#1888). Sized comfortably above any
# legitimate contention chain this module's consumers exercise — the shared
# concurrency regression test's worst case is 8 workers x 60ms holds (~480ms
# of legitimate queueing; see test_lock_acquire_budget_exceeds_worst_case_
# contention, which pins this relationship mechanically) — so normal
# contention still fully serializes and only a genuinely stalled holder ever
# trips the give-up path.
_DEFAULT_LOCK_ACQUIRE_BUDGET_SECONDS = 2.0
_LOCK_POLL_INTERVAL_SECONDS = 0.01

# Hard ceiling on the test-only override below (security review, #1888): the
# override has a floor to stop a misconfigured `0` from removing the retry,
# but nothing stopped the OTHER direction — an arbitrarily large value would
# reinstate exactly the unbounded wait this module exists to remove. No
# configuration can raise the give-up bound past this.
_MAX_LOCK_ACQUIRE_BUDGET_SECONDS = 10.0

# `_try_acquire`'s non-blocking attempt raises OSError both for ordinary lock
# contention (retry-worthy) and for conditions retrying can never fix — e.g.
# ENOLCK/EOPNOTSUPP when flock isn't supported on the underlying filesystem
# (some NFS/FUSE/CIFS mounts). Without this distinction, `_acquire_bounded`
# burned the full budget on every single call on such a filesystem, which is
# strictly worse than the pre-#1888 behavior (an immediate, un-retried
# failure) it must not regress. Only these errnos — genuine "someone else
# holds it" signals on POSIX (`flock`) and Windows (`msvcrt.locking`) — are
# worth retrying; anything else gives up immediately.
_LOCK_CONTENTION_ERRNOS = frozenset(
    e
    for e in (errno.EACCES, errno.EAGAIN, getattr(errno, "EWOULDBLOCK", None))
    if e is not None
)


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


def _lock_acquire_budget_seconds() -> float:
    """Test-only override for the give-up budget, mirroring
    `race_window_delay`'s env-var injection pattern below. Unset in
    production; an unset, negative, or non-integer value (the var is
    documented in whole milliseconds) falls back to the default (fail-open).
    Clamped to `[_LOCK_POLL_INTERVAL_SECONDS,
    _MAX_LOCK_ACQUIRE_BUDGET_SECONDS]`: the floor guarantees a nonzero
    budget (not a guaranteed retry count — a first attempt that itself takes
    longer than the floor can still see zero retries), and the ceiling
    guarantees no override can reinstate an effectively-unbounded wait.
    """
    raw = os.environ.get("DEV_TEAM_LOCK_ACQUIRE_BUDGET_TEST_MS")
    if not raw:
        return _DEFAULT_LOCK_ACQUIRE_BUDGET_SECONDS
    try:
        value_seconds = int(raw) / 1000
    except ValueError:
        return _DEFAULT_LOCK_ACQUIRE_BUDGET_SECONDS
    if value_seconds < 0:
        return _DEFAULT_LOCK_ACQUIRE_BUDGET_SECONDS
    return min(
        _MAX_LOCK_ACQUIRE_BUDGET_SECONDS,
        max(_LOCK_POLL_INTERVAL_SECONDS, value_seconds),
    )


def _try_acquire(handle) -> bool:
    """One non-blocking acquisition attempt on `handle`.

    Returns True on success, False if nothing raised but no lock backend is
    available (fcntl/msvcrt both missing) — this is the one case where
    `_acquire_bounded` below returns without ever polling or sleeping, since
    retrying an operation that can't succeed either way buys nothing. Raises
    OSError when the lock is currently held elsewhere — the caller decides
    whether to retry or give up.
    """
    if fcntl is not None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    if msvcrt is not None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return True
    return False


def _release(handle) -> None:
    """Release a lock previously acquired via `_try_acquire`, mirroring its
    guard-clause style. Can raise OSError; the caller (`locked_state`) wraps
    this call in its own try/except, matching the fail-open contract."""
    if fcntl is not None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return
    if msvcrt is not None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def _acquire_bounded(handle) -> bool:
    """Poll `_try_acquire` until it succeeds, the acquire budget elapses, or
    (immediately, no polling) `_try_acquire` signals a condition retrying
    can't fix — no lock backend at all, or an OSError that isn't ordinary
    contention (see `_LOCK_CONTENTION_ERRNOS`).

    Returns True once the lock is held, False if the budget ran out with the
    lock still held elsewhere, no backend exists, or a non-contention
    OSError occurred (the caller runs unlocked in every False case).
    """
    deadline = time.monotonic() + _lock_acquire_budget_seconds()
    while True:
        try:
            return _try_acquire(handle)
        except OSError as exc:
            if exc.errno not in _LOCK_CONTENTION_ERRNOS:
                return False
            if time.monotonic() >= deadline:
                return False
            time.sleep(_LOCK_POLL_INTERVAL_SECONDS)


@contextlib.contextmanager
def locked_state(path: Path) -> Iterator[None]:
    """Hold an exclusive advisory lock for a full read-modify-write cycle.

    Prevents the lost-update race where two concurrent invocations both read
    the same stale value, both increment it, and one write clobbers the
    other. `fcntl.flock` on POSIX, `msvcrt.locking` on Windows (this repo's
    hooks target both — ADR 0014/0015). The lock file lives beside `path` as
    `<path>.lock`.

    Acquisition is bounded, not a blocking wait (#1888): a stalled holder
    trips a fail-open give-up after `_lock_acquire_budget_seconds()` of
    polling rather than blocking a caller indefinitely.

    Fail-open: a missing `fcntl` *and* `msvcrt`, an OSError creating the lock
    file's parent directory or opening the lock file, or a lock that can't be
    acquired within budget, all fall through to running the critical section
    UNLOCKED rather than raising or blocking forever. An unlocked lost-update
    is no worse than the pre-#1501 behavior; a crash — or an undelivered
    guard-hook verdict — would be worse, and these hooks are advisory.
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
                    locked = _acquire_bounded(handle)
                except OSError:
                    locked = False
                yield
            finally:
                if locked:
                    try:
                        _release(handle)
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
