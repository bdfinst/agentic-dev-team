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
these are advisory nudges, never gates — unless a caller opts into
`locked_state(path, strict=True)`, in which case the same failure raises
`RuntimeError` instead of running unlocked.

Lock *acquisition* is bounded, not a blocking wait (#1888): a hung sibling
process holding the lock must never leave a caller blocked indefinitely,
since some callers (e.g. `boundary_events.py`, per #1874) sit in front of a
safety-critical guard hook's verdict. `locked_state` polls a non-blocking
acquisition for a bounded total budget and falls through to running the
critical section UNLOCKED once that budget elapses — the same fail-open
posture as every other failure mode here. This bounds contention on an
already-held lock specifically; it does NOT bound a stall inside `open()` on
the lock file itself, or inside a caller's own I/O in the critical section —
a wedged mount can still block there. Every one of these fail-open points is
skippable per call: pass `strict=True` to `locked_state` and the same failure
raises `RuntimeError` instead of running unlocked — for a caller (e.g. a
read-modify-write whose lost update is a correctness bug, not an advisory
nudge) that must never silently proceed without the lock.

A second use case (#1889) reuses `locked_state` for pure append-serialization
rather than read-modify-write: several `.claude/metrics/*.jsonl` telemetry
streams have concurrent writers of their own — sliced-mode code-review's 2-3
parallel slices, `/build`'s wave-parallel fan-out
(`DEV_TEAM_MAX_PARALLEL_BUILDS`), or two sessions/worktrees appending to the
same shared log. Without the lock, two processes' `write()` calls can
interleave mid-line and corrupt the stream for every downstream consumer.
`append_line_locked(path, line)` below is the shared helper for that shape.

The lock file is opened with `O_NOFOLLOW` (where the platform defines it)
and created at mode `0600` (security review, #1889): a pre-planted symlink
at `<path>.lock` would otherwise be followed by a plain `open()`, and a
world/group-writable lock file would let another local user on a shared
host acquire and hold it (an `flock`/`msvcrt.locking` caller needs no write
access to the *data* file to do this — only to the lock file). `O_NOFOLLOW`
makes `open()` fail closed (OSError) on a symlinked lock path, which this
function's existing fail-open contract already turns into an unlocked
critical section — the same outcome as any other lock-open failure.

Stdlib-only.
"""

from __future__ import annotations

import contextlib
import errno
import os
import sys
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
#
# EDEADLOCK/EDEADLK (#1904 item 9, defensive — no recorded Windows probe):
# Windows CRT `_locking` (the backend behind `msvcrt.locking`) documents
# surfacing a deadlock-shaped errno on contention in some circumstances. Both
# are POSIX-optional attributes (absent on some platforms), hence the same
# `getattr(..., None)` + filter idiom already used for EWOULDBLOCK above.
_LOCK_CONTENTION_ERRNOS = frozenset(
    e
    for e in (
        errno.EACCES,
        errno.EAGAIN,
        getattr(errno, "EWOULDBLOCK", None),
        getattr(errno, "EDEADLOCK", None),
        getattr(errno, "EDEADLK", None),
    )
    if e is not None
)


class LockAcquisitionError(RuntimeError):
    """Raised by `locked_state(path, strict=True)` when the lock could not be
    acquired (directory/lock-file creation failure, fdopen failure, or
    acquire-budget exhaustion) — never for a caller-raised exception from
    inside the critical section (#1892 still applies unchanged). Subclasses
    `RuntimeError` so pre-existing `pytest.raises(RuntimeError, ...)`
    assertions against strict-mode callers keep passing; new callers should
    narrow to this type specifically so a broad `except (OSError,
    RuntimeError)` doesn't also swallow an unrelated `RuntimeError` raised by
    the critical section body itself (#1920 correctness review)."""


def _reraise_unless_fail_open(exc: OSError, fail_open: bool) -> None:
    """Re-raise `exc` unless `fail_open` — the shared decision behind each
    of `atomic_write`'s OSError sites (#1920 structure review: this
    collapses the same duplication `_refuse_or_warn` above was extracted to
    eliminate for `locked_state`'s four fail-open sites). Takes the
    exception explicitly, rather than relying on a bare `raise` re-raising
    the caller's currently-handled exception, so this helper is an ordinary
    function call rather than something that only works from inside a
    lexical `except` block.
    """
    if not fail_open:
        raise exc


def atomic_write(path: Path, text: str, *, fail_open: bool = True) -> None:
    """Write `text` to `path` atomically via tempfile-in-same-dir + rename.

    A concurrent reader sees either the old file or the fully-written new one,
    never a partial write.

    `fail_open` (default `True`, matching every pre-existing caller's call
    shape): any OSError — creating the parent directory, obtaining the temp
    file, opening/writing it, or the final `os.replace` — short-circuits to a
    silent no-op; persistence is best-effort for these advisory hooks. Pass
    `fail_open=False` for a caller that must never silently proceed without
    having actually written the file (mirrors `append_line_locked`'s own
    `fail_open` parameter, #1920): the same OSError re-raises instead, after
    the same best-effort tmp-file cleanup runs either way.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        _reraise_unless_fail_open(exc, fail_open)
        return
    try:
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{path.name}-", suffix=".tmp", dir=str(path.parent)
        )
    except OSError as exc:
        _reraise_unless_fail_open(exc, fail_open)
        return
    try:
        try:
            handle = os.fdopen(fd, "w", encoding="utf-8")
        except OSError:
            # fdopen() failed without ever wrapping fd in a file object, so
            # nothing else will close it — leaking the fd otherwise (#1920
            # correctness review; mirrors locked_state's own fdopen-failure
            # fd-leak fix).
            with contextlib.suppress(OSError):
                os.close(fd)
            raise
        with handle:
            handle.write(text)
        os.replace(tmp_name, path)
    except OSError as exc:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        _reraise_unless_fail_open(exc, fail_open)


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


def _refuse_or_warn(
    reason: str, path: Path, strict: bool, exc: BaseException | None = None
) -> None:
    """Shared decision behind each of `locked_state`'s four fail-open
    points (#1892's scoping invariant is unaffected — every call site below
    still runs its own `yield`/`return` immediately after this returns; this
    helper never yields itself). `strict=True` raises
    `LockAcquisitionError`, chaining `exc` as its cause when one is given
    (the budget-exhaustion site has no underlying exception to chain, so it
    omits `exc`). `strict=False` prints the fail-open diagnostic to stderr
    and returns, leaving the caller to fall through to running the critical
    section unlocked.
    """
    if strict:
        message = (
            f"{reason}; refusing to run the critical section unlocked for {path}"
        )
        if exc is not None:
            raise LockAcquisitionError(message) from exc
        raise LockAcquisitionError(message)
    print(f"{reason}; proceeding WITHOUT lock for {path}", file=sys.stderr)


@contextlib.contextmanager
def locked_state(path: Path, *, strict: bool = False) -> Iterator[None]:
    """Hold an exclusive advisory lock for a full read-modify-write cycle.

    Prevents the lost-update race where two concurrent invocations both read
    the same stale value, both increment it, and one write clobbers the
    other. `fcntl.flock` on POSIX, `msvcrt.locking` on Windows (this repo's
    hooks target both — ADR 0014/0015). The lock file lives beside `path` as
    `<path>.lock`.

    Acquisition is bounded, not a blocking wait (#1888): a stalled holder
    trips a fail-open give-up after `_lock_acquire_budget_seconds()` of
    polling rather than blocking a caller indefinitely.

    Fail-open (default, `strict=False`): a missing `fcntl` *and* `msvcrt`, an
    OSError creating the lock file's parent directory or opening the lock
    file, or a lock that can't be acquired within budget, all fall through to
    running the critical section UNLOCKED rather than raising or blocking
    forever. An unlocked lost-update is no worse than the pre-#1501 behavior;
    a crash — or an undelivered guard-hook verdict — would be worse, and
    these hooks are advisory.

    `strict=True`: every one of the same four fail-open points above raises
    `LockAcquisitionError` (a `RuntimeError` subclass, carrying the same
    diagnostic detail the fail-open path would otherwise print to stderr,
    reworded to say the critical section is being refused rather than run
    unlocked) instead of printing and running the critical section unlocked
    — the critical section body never runs when the lock could not be
    acquired. For a caller where a lost update is a correctness bug rather
    than an advisory best-effort nudge. Every existing caller passes the
    default `False` and is completely unaffected; this is an additive,
    backward-compatible parameter.

    A caller-raised OSError from inside the critical section propagates
    normally (through the `finally`/release, out of this generator's
    `yield`) rather than being swallowed (#1892): the `except OSError` that
    guards the `os.fdopen()` call is scoped to that call alone, not to the
    `with` block around the `yield` — a prior version wrapped both, which
    meant a caller's OSError landed in that same `except`, fell through to a
    second bare `yield`, and made `contextlib` raise
    `RuntimeError("generator didn't stop after throw()")` instead of the
    OSError the caller actually raised.
    """
    lock_path = path.parent / (path.name + ".lock")
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        reason = (
            f"atomic_state: lock acquisition failed (could not create lock "
            f"directory {lock_path.parent}: {exc})"
        )
        _refuse_or_warn(reason, path, strict, exc)
        yield
        return

    # os.O_NOFOLLOW is undefined on Windows; getattr(..., 0) makes the flag
    # a no-op there rather than an AttributeError (which isn't an OSError
    # and would escape the except below).
    try:
        lock_fd = os.open(
            str(lock_path), os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600
        )
        # The mode argument to os.open() only applies when O_CREAT actually
        # creates the file — POSIX ignores it for a path that already
        # exists. Every checkout that already has a pre-#1889 lock file on
        # disk (created at the old, wider default permissions) would
        # otherwise keep it forever. fchmod on the already-open fd (no
        # TOCTOU) enforces 0600 either way (security review, #1889).
        with contextlib.suppress(OSError, AttributeError):
            os.fchmod(lock_fd, 0o600)
    except OSError as exc:
        reason = (
            f"atomic_state: lock acquisition failed (could not open lock "
            f"file {lock_path}: {exc})"
        )
        _refuse_or_warn(reason, path, strict, exc)
        yield
        return

    # This except is scoped to the fdopen() call ONLY (#1892) — it must NOT
    # also wrap the `with` block below, or a caller-raised OSError from
    # inside the critical section (at the `yield`) would be caught here too
    # and mishandled (see the CONTRACT note above).
    try:
        handle_cm = os.fdopen(lock_fd, "r+")
    except OSError as exc:
        # fdopen() failed without ever wrapping lock_fd in a file object, so
        # nothing else will close it — leaking the fd otherwise (#1920
        # correctness review).
        with contextlib.suppress(OSError):
            os.close(lock_fd)
        reason = (
            f"atomic_state: lock acquisition failed (fdopen on "
            f"{lock_path} failed: {exc})"
        )
        _refuse_or_warn(reason, path, strict, exc)
        yield
        return

    with handle_cm as handle:
        locked = False
        try:
            try:
                locked = _acquire_bounded(handle)
            except OSError:
                locked = False
            if not locked:
                reason = (
                    f"atomic_state: lock acquisition failed (budget exhausted "
                    f"or non-contention error acquiring {lock_path})"
                )
                _refuse_or_warn(reason, path, strict)
            yield
        finally:
            if locked:
                try:
                    _release(handle)
                except OSError:
                    pass


def _write_maybe_delayed(handle, line: str, delay_env_var: str | None) -> None:
    """Write `line` in one call, unless `delay_env_var` names a set env var.

    Test-only split path: see `append_line_locked`'s docstring for why a
    single small `write()` needs splitting, not just delaying, to simulate a
    genuinely non-atomic write. A value of ``"0"`` (or anything else that
    parses to <= 0, or fails to parse at all) takes the plain single-write
    path — matching this repo's `DEV_TEAM_*` numeric-knob convention where a
    non-positive value means "disabled" — rather than bare `os.environ.get()`
    truthiness, which would treat the *string* ``"0"`` as "enabled with a
    zero-length delay" and needlessly split the write.
    """
    delay_ms = 0
    if delay_env_var:
        raw = os.environ.get(delay_env_var)
        if raw:
            try:
                delay_ms = int(raw)
            except ValueError:
                delay_ms = 0
    if delay_ms <= 0:
        handle.write(line)
        return
    mid = len(line) // 2
    handle.write(line[:mid])
    handle.flush()
    race_window_delay(delay_env_var)
    handle.write(line[mid:])


def append_line_locked(
    path: Path,
    line: str,
    *,
    delay_env_var: str | None = None,
    fail_open: bool = True,
) -> None:
    """Append `line` (already newline-terminated) to `path` under `locked_state`.

    Serializes concurrent appends to a shared JSONL stream: while the lock is
    held (see `locked_state`'s own fail-open fallback above for when it might
    not be), two processes writing at once cannot interleave their bytes
    into one corrupted line (see module docstring, #1889) — the append-only
    counterpart to `locked_state`'s original read-modify-write use case. The
    lock is what provides this, regardless of how many underlying
    `os.write()` syscalls a single logical `.write()` call happens to
    decompose into (e.g. a line long enough to cross the `BufferedWriter`'s
    internal buffer boundary) — a caller does not need to reason about
    syscall-level atomicity separately.

    `fail_open` (default `True`): OSError from `open()`/`write()` is caught
    *inside* the lock and discarded, matching this repo's fail-open posture
    for advisory telemetry. Pass `fail_open=False` for a caller that needs
    the write failure to propagate instead (e.g. a round-log CLI that must
    crash rather than silently record nothing) — the OSError is still
    caught *inside* the lock (avoiding a caller-raised exception crossing
    the generator's `yield`), just re-raised after the lock releases rather
    than discarded.

    `delay_env_var`, when set and naming a set env var, splits the write into
    two separate `write()` calls with `race_window_delay` between them,
    instead of the usual single call. This is a test-only hook, needed
    because a single small `write()` to an `O_APPEND`-opened file is
    typically atomic with respect to other processes on mainstream local
    filesystems (not independently verified here — no recorded runtime
    probe), so simply sleeping *before* an unsplit write may not force real
    interleaving in a test. The split instead simulates a genuinely
    non-atomic write directly (long enough to cross a write-buffer
    boundary, or a filesystem, e.g. some NFS configurations, that doesn't
    honor `O_APPEND`'s atomicity guarantee) — the actual failure mode the
    lock protects against regardless of whether any given production write
    happens to be single-syscall-atomic on its own. Unset (the default) in
    production: exactly one `.write()` call at this Python API level,
    unchanged from the code this helper replaced.
    """
    write_error: OSError | None = None
    with locked_state(path):
        try:
            # O_NOFOLLOW (security review, #1889): the data file sits beside
            # the now-hardened `<path>.lock` in the same predictable,
            # repo-relative directory — a pre-planted symlink here would
            # otherwise redirect every append the same way the pre-fix lock
            # file did. Mode is the historical default (not 0600): unlike
            # the lock file, this file's readers are other tooling that
            # expects normal permissions.
            fd = os.open(
                str(path),
                os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
                0o644,
            )
            with os.fdopen(fd, "a", encoding="utf-8") as handle:
                _write_maybe_delayed(handle, line, delay_env_var)
        except OSError as exc:
            if not fail_open:
                write_error = exc
    if write_error is not None:
        raise write_error


_MAX_RACE_WINDOW_DELAY_MS = 500


def race_window_delay(env_var: str) -> None:
    """Test-only injection point: sleep inside a locked critical section when
    `env_var` names a millisecond delay, widening the race window so a
    concurrency test can deterministically force two invocations to overlap
    rather than relying on timing luck. Unset in production; a bad/missing
    value is a no-op (fail-open). NOT the same implementation as
    `code_intelligence_turn_mark._test_delay` despite the similar shape —
    that sibling still has an uncapped sleep inside its own blocking lock.

    Capped at `_MAX_RACE_WINDOW_DELAY_MS` (security review, #1889): several
    callers now invoke this from inside a held exclusive lock on a shared,
    frequently-hit stream (`append_line_locked`'s `_write_maybe_delayed`), so
    an unbounded value here would let anything that can influence the process
    environment hold that lock for an attacker-chosen duration. Every real
    test uses 60ms; the cap costs them nothing. This bounds one call, not a
    whole critical section — a caller invoking it more than once, or from
    inside a loop, multiplies the total; today's callers all call it exactly
    once per critical section, but that is a property of the call sites,
    not an invariant this function enforces.
    """
    raw = os.environ.get(env_var)
    if not raw:
        return
    try:
        time.sleep(min(int(raw), _MAX_RACE_WINDOW_DELAY_MS) / 1000)
    except (ValueError, OSError):
        pass
