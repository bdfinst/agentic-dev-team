"""Find SQL text in a file: whole ``.sql`` files and, later, embedded strings.

``extract(path, text)`` returns the SQL fragments the detector scans. A
``.sql`` file is one fragment that starts at line 1.

Extension point for embedded SQL
--------------------------------

Embedded-source extraction (string literals in ``.py``, ``.ts``, ``.js``,
``.cs``, and ``.java`` files) is a later slice. It registers one function per
file suffix in ``EMBEDDED_EXTRACTORS``:

    EMBEDDED_EXTRACTORS[".py"] = extract_python  # (text: str) -> Extraction

An embedded extractor returns the SQL-shaped literals as ``Fragment`` objects
and counts concatenated or interpolated literals it cannot scan in
``Extraction.skipped``. Registered suffixes are scanned automatically and
count toward the gate.

Stdlib-only. Python 3.10+.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ORIGIN_SQL = "sql"
ORIGIN_EMBEDDED = "embedded"
SQL_SUFFIX = ".sql"


@dataclass(frozen=True)
class Fragment:
    """SQL text and the number of host-file lines before its first line."""

    text: str
    line_offset: int = 0
    origin: str = ORIGIN_SQL


@dataclass(frozen=True)
class Extraction:
    """Scannable fragments and the count of SQL-shaped literals skipped.

    A skipped literal is SQL-shaped, so it counts as SQL present.
    """

    fragments: tuple[Fragment, ...] = ()
    skipped: int = 0

    @property
    def sql_present(self) -> bool:
        return bool(self.fragments) or self.skipped > 0


#: suffix -> extractor. Filled by the embedded-source slice; empty today.
EMBEDDED_EXTRACTORS: dict[str, Callable[[str], Extraction]] = {}


def is_sql_file(path: str) -> bool:
    return Path(path).suffix.lower() == SQL_SUFFIX


def handles(path: str) -> bool:
    """True when the detector reads this file at all."""
    return is_sql_file(path) or Path(path).suffix.lower() in EMBEDDED_EXTRACTORS


def extract(path: str, text: str) -> Extraction:
    """SQL fragments of one file. Files the detector does not handle yield none."""
    if is_sql_file(path):
        return Extraction((Fragment(text),))
    extractor = EMBEDDED_EXTRACTORS.get(Path(path).suffix.lower())
    return extractor(text) if extractor else Extraction()
