"""Signal helpers for the A/B harness's interrupt tests."""

from __future__ import annotations

import signal
import threading

import ab_harness_path  # noqa: F401  (puts the harness on sys.path first)

TERMINATION_SIGNALS = (signal.SIGTERM, signal.SIGHUP)


def raise_keyboard_interrupt(_signum, _frame) -> None:
    raise KeyboardInterrupt


INTERRUPT_SIGNALS = (signal.SIGINT, *TERMINATION_SIGNALS)


def blocked_signals() -> set[signal.Signals]:
    return set(signal.pthread_sigmask(signal.SIG_BLOCK, []))


def note_signal(_signum, _frame) -> None:
    """A harmless handler: the signal is delivered and nothing else happens."""


def signal_own_thread(signum: int) -> None:
    """Deliver `signum` to the test's own thread, where `interrupts` holds it back.

    `os.kill(os.getpid(), ...)` is process-directed, so the kernel may hand the
    signal to any thread that does not block it. A pytest-xdist worker runs a second
    OS thread (execnet's receiver, invisible to `threading`) that blocks nothing, so
    the signal can bypass the mask the test set on its own thread and is never seen
    pending there. A thread-directed signal stays pending on the thread that blocks it.
    """
    signal.pthread_kill(threading.main_thread().ident, signum)
