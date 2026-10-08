"""Hold the signals that end a run back until a point where the run can act on them.

Ctrl-C, SIGTERM and SIGHUP are blocked for the whole run, from the first trial to
the saved artifact, so none of them can raise inside bookkeeping, grading or the
write and cost a paid result. They stay pending in the kernel instead, and the run
looks at them between steps: the runner while it waits on a trial's process, the
trial loop before it starts the next trial, and the session once the artifact is
saved. A signal that is acted on is consumed, so it is never delivered later.

`termination_as_interrupt` covers the time before the run holds the signals: there
SIGTERM and SIGHUP act like Ctrl-C and raise `KeyboardInterrupt`.
"""

from __future__ import annotations

import signal
from collections.abc import Iterator
from contextlib import contextmanager

# SIGHUP is absent on Windows; the harness is POSIX-only for other reasons too.
TERMINATION_SIGNALS = tuple(
    getattr(signal, name) for name in ("SIGTERM", "SIGHUP") if hasattr(signal, name)
)
INTERRUPT_SIGNALS = frozenset({signal.SIGINT, *TERMINATION_SIGNALS})


def _live_signals() -> frozenset[signal.Signals]:
    """The interrupt signals this process does not ignore.

    A signal the process was started ignoring (`nohup` ignores SIGHUP) must not
    end the run, and an ignored signal that is blocked would still queue as pending.
    """
    return frozenset(
        signum
        for signum in INTERRUPT_SIGNALS
        if signal.getsignal(signum) is not signal.SIG_IGN
    )


def block() -> set[signal.Signals]:
    """Hold the interrupt signals back; return the mask to pass to `restore`."""
    return signal.pthread_sigmask(signal.SIG_BLOCK, _live_signals())


def restore(previous: set[signal.Signals]) -> None:
    """Put back the mask `block` returned. A signal still pending is delivered now."""
    signal.pthread_sigmask(signal.SIG_SETMASK, previous)


def take_pending() -> bool:
    """Consume the interrupt signals that arrived while held; say whether there were any."""
    pending = signal.sigpending() & _live_signals()
    for signum in pending:
        # Each is pending, so this returns at once and removes it.
        signal.sigwait({signum})
    return bool(pending)


def restore_reporting(previous: set[signal.Signals]) -> bool:
    """Consume what is pending, put back the mask, and say whether a signal arrived.

    A signal that lands after the consume and before the restore is delivered by the
    restore as `KeyboardInterrupt`; it is caught here and counted, so none escapes.
    """
    arrived = take_pending()
    while True:
        try:
            restore(previous)
        except KeyboardInterrupt:
            # The mask is already back; a further signal may still be waiting to be raised.
            arrived = True
        else:
            return arrived


def _raise_interrupt(_signum, _frame) -> None:
    raise KeyboardInterrupt


@contextmanager
def termination_as_interrupt() -> Iterator[None]:
    """Make SIGTERM and SIGHUP raise `KeyboardInterrupt`; restore the old handlers on exit.

    A signal the process was started ignoring (`nohup` ignores SIGHUP) stays ignored.
    """
    previous = {
        signum: signal.signal(signum, _raise_interrupt)
        for signum in TERMINATION_SIGNALS
        if signal.getsignal(signum) is not signal.SIG_IGN
    }
    try:
        yield
    finally:
        for signum, handler in previous.items():
            # `signal.signal` returns None for a handler not installed from Python.
            signal.signal(signum, handler if handler is not None else signal.SIG_DFL)
