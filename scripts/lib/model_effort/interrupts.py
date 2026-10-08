"""Treat the signals that end a run the way Ctrl-C ends it: as a `KeyboardInterrupt`.

The run then keeps its completed trials and writes the artifact, instead of the
process dying with the paid results unwritten.
"""

from __future__ import annotations

import signal
from collections.abc import Iterator
from contextlib import contextmanager

# SIGHUP is absent on Windows; the harness is POSIX-only for other reasons too.
TERMINATION_SIGNALS = tuple(
    getattr(signal, name) for name in ("SIGTERM", "SIGHUP") if hasattr(signal, name)
)


def _raise_interrupt(_signum, _frame) -> None:
    raise KeyboardInterrupt


@contextmanager
def termination_as_interrupt() -> Iterator[None]:
    """Make SIGTERM and SIGHUP raise `KeyboardInterrupt`; restore the old handlers on exit."""
    previous = {
        signum: signal.signal(signum, _raise_interrupt)
        for signum in TERMINATION_SIGNALS
    }
    try:
        yield
    finally:
        for signum, handler in previous.items():
            # `signal.signal` returns None for a handler not installed from Python.
            signal.signal(signum, handler if handler is not None else signal.SIG_DFL)
