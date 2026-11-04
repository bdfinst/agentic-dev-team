"""doctor_files.py - the bounded file reader behind ``/doctor``'s checks.

Reads files ``/doctor`` does not own without hanging, over-reading or raising
on the ordinary ways a path goes wrong: missing, a directory or named pipe in
its place, too large, not JSON, not a JSON object.

Stdlib only, no local imports. The top level stays parseable by Python 3.8
(see ``doctor.py``).
"""

from __future__ import annotations

import dataclasses
import enum
import json
import os
import stat
from pathlib import Path
from typing import Any

#: The most bytes ``/doctor`` reads from any one file it does not own.
MAX_FILE_BYTES = 1 << 20


class LoadKind(enum.Enum):
    """How reading a file ended."""

    MISSING = "missing"
    NOT_REGULAR = "not-regular"
    TOO_LARGE = "too-large"
    INVALID = "invalid"
    NOT_OBJECT = "not-object"
    LOADED = "loaded"


@dataclasses.dataclass(frozen=True)
class LoadResult:
    """A file read: ``kind`` says how, ``data`` is the content when ``LOADED``."""

    kind: LoadKind
    data: Any = None


def open_nonblocking(path: str, flags: int) -> int:
    """``open`` opener that never waits on a named pipe with no writer."""
    return os.open(path, flags | getattr(os, "O_NONBLOCK", 0))


def read_bounded(path: Path) -> LoadResult:
    """The bytes of a regular file of at most ``MAX_FILE_BYTES``, else why not.

    ``LOADED`` carries the bytes; ``MISSING``, ``NOT_REGULAR`` and ``TOO_LARGE``
    carry none. Other ``OSError`` propagates. At most ``MAX_FILE_BYTES + 1``
    bytes are read; the extra byte only detects an oversize file.
    """
    try:
        with open(path, "rb", opener=open_nonblocking) as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                return LoadResult(LoadKind.NOT_REGULAR)
            data = handle.read(MAX_FILE_BYTES + 1)
    except (FileNotFoundError, NotADirectoryError):
        return LoadResult(LoadKind.MISSING)
    except IsADirectoryError:
        return LoadResult(LoadKind.NOT_REGULAR)
    if len(data) > MAX_FILE_BYTES:
        return LoadResult(LoadKind.TOO_LARGE)
    return LoadResult(LoadKind.LOADED, data)


def load_json(path: Path) -> LoadResult:
    """Read ``path`` as a JSON object; other OSErrors propagate to the caller."""
    raw = read_bounded(path)
    if raw.kind is not LoadKind.LOADED:
        return raw
    try:
        data = json.loads(raw.data.decode("utf-8"))
    except ValueError:  # JSONDecodeError and UnicodeDecodeError
        return LoadResult(LoadKind.INVALID)
    if not isinstance(data, dict):
        return LoadResult(LoadKind.NOT_OBJECT)
    return LoadResult(LoadKind.LOADED, data)
