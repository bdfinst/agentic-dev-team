"""Hold the signals that end a run back until a point where the run can act on them.

Ctrl-C, SIGTERM and SIGHUP are blocked for the whole run, from the first trial to
the saved artifact, so none of them can raise inside bookkeeping, grading or the
write and cost a paid result. They stay pending in the kernel instead, and the run
looks at them between steps: the runner while it waits on a trial's process, the
trial loop before it starts the next trial, and the session once the artifact is
saved. A signal that is acted on is consumed, so it is never delivered later.

`RunGuard` owns that protocol for a run: it blocks the signals, notes that the run
started, and on the way out consumes what is pending, puts the mask back and
absorbs a signal that lands as it does. `termination_as_interrupt` covers the time
outside the guard: there SIGTERM and SIGHUP act like Ctrl-C and raise
`KeyboardInterrupt`, which the caller reports as before or after the run by asking
the guard whether it `started`.
"""

from __future__ import annotations

import signal
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

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


def pending() -> bool:
    """True when an interrupt signal is waiting; leave it pending for the run to act on."""
    return bool(signal.sigpending() & _live_signals())


@contextmanager
def held_signals() -> Iterator[None]:
    """Hold the interrupt signals for the body, so a step that must finish is not cut short.

    On exit the mask is put back and a signal that arrived meanwhile is delivered
    then, as `KeyboardInterrupt`, after the body has finished.
    """
    previous = block()
    try:
        yield
    finally:
        restore(previous)


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


@dataclass
class RunGuard:
    """The hold on the interrupt signals for one run, and what it learned.

    `started` turns true when the signals are held and stays true, so a caller that
    later gets a `KeyboardInterrupt` can tell the run had begun. `arrived` is true
    after `held` exits when a signal came that nothing acted on: one still pending
    at the end, one delivered as the mask was restored, or a `KeyboardInterrupt`
    raised by the body.
    """

    started: bool = False
    arrived: bool = False

    @contextmanager
    def held(self) -> Iterator[None]:
        """Hold the interrupt signals for the body; free them, and set `arrived`, on exit.

        A `KeyboardInterrupt` that reaches this point, from the body or from the
        restore, is absorbed: the signals are free again and the run is over. Any
        other exception propagates after the signals are restored.
        """
        previous_mask = block()
        self.started = True
        try:
            try:
                yield
            finally:
                self.arrived = restore_reporting(previous_mask)
        except KeyboardInterrupt:
            self.arrived = True


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
