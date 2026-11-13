"""Shared pieces of the stdin-hang tests: the refusal marker, platform skips,
the refusal assertion, and the stdin kinds that never reach EOF."""

from __future__ import annotations

import contextlib
import os
import socket
import subprocess
import sys
from collections.abc import Iterator

import pytest

#: Text the guard puts in every refusal message.
REFUSAL = "stdin never reaches EOF"

#: Per-subprocess limit. A regression that blocks on stdin fails the row with
#: a timeout instead of hanging the run.
SUBPROCESS_TIMEOUT_SECONDS = 30

NO_SOCKETS_ON_WINDOWS = pytest.mark.skipif(
    sys.platform == "win32",
    reason="fstat cannot tell a socket from a pipe on Windows",
)
NO_PTY_ON_WINDOWS = pytest.mark.skipif(
    sys.platform == "win32", reason="the pty module does not exist on Windows"
)


def assert_refused(result: subprocess.CompletedProcess, flag: str) -> None:
    """The run exited 2 with nothing on stdout and a refusal naming ``flag``."""
    # The literal 2 is deliberate: an independent oracle for the guard's constant.
    assert result.returncode == 2, result.stderr
    assert result.stdout == "", result.stderr
    assert REFUSAL in result.stderr, result.stderr
    assert flag in result.stderr, result.stderr


def fallback_lines(stderr: str) -> list[str]:
    """The stderr lines that report a stdin that never reaches EOF."""
    return [line for line in stderr.splitlines() if REFUSAL in line]


@contextlib.contextmanager
def endless_socket() -> Iterator[socket.socket]:
    """The read end of a socket pair whose peer stays open and silent: a read
    of it never reaches EOF."""
    reader, peer = socket.socketpair()
    try:
        yield reader
    finally:
        reader.close()
        peer.close()


@contextlib.contextmanager
def terminal() -> Iterator[int]:
    """The slave end of a pseudo-terminal; skips where none can be opened."""
    import pty

    try:
        master, slave = pty.openpty()
    except OSError as exc:
        pytest.skip(f"no pseudo-terminal available: {exc}")
    try:
        yield slave
    finally:
        os.close(master)
        os.close(slave)
