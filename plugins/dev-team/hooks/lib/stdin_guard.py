"""stdin_guard - refuse stdin streams that never reach EOF.

Claude Code's Bash tool gives a command a socket on stdin that never closes.
A script that reads stdin by default then blocks until the tool times out.
``read_stdin_or_exit`` reads a stream only when its type can end, and
otherwise exits with a usage error that names the flag to pass instead.

Limits: a pipe whose writer never closes is not detected, and a socket that
delivers data and then EOF is refused too (the caller passes the flag or
pipes the input).

Stdlib only.
"""

from __future__ import annotations

import io
import os
import stat
import sys

REFUSAL_EXIT_STATUS = 2


def stdin_is_readable(stream=None) -> bool:
    """True when reading ``stream`` (default ``sys.stdin``) can reach EOF.

    Inspects the descriptor of the given stream, never the process's fd 0.
    A stream with no descriptor (an in-memory stream) is readable.
    """
    if stream is None:
        stream = sys.stdin
    if stream is None or getattr(stream, "closed", False):
        return False
    try:
        fd = stream.fileno()
    except (io.UnsupportedOperation, ValueError):
        return True
    except OSError:
        return False
    try:
        mode = os.fstat(fd).st_mode
    except OSError:
        return False
    if stat.S_ISFIFO(mode) or stat.S_ISREG(mode):
        return True
    return stat.S_ISCHR(mode) and not os.isatty(fd)


def read_stdin_or_exit(flag: str, stream=None) -> str:
    """Return the text of ``stream`` (default ``sys.stdin``), or exit 2.

    A stream that can hang is refused with one stderr message naming ``flag``;
    nothing goes to stdout.
    """
    if stream is None:
        stream = sys.stdin
    if stdin_is_readable(stream):
        return stream.read()
    script = os.path.basename(sys.argv[0])
    sys.stderr.write(
        f"{script}: no input; stdin never reaches EOF here (terminal or open "
        f"socket). Pass {flag} <file> or pipe the input in.\n"
    )
    sys.exit(REFUSAL_EXIT_STATUS)
