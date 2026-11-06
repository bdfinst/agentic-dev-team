"""Find SQL text in a file: whole ``.sql`` files and SQL-shaped string literals.

``extract(path, text)`` returns the SQL fragments the detector scans. A
``.sql`` file is one fragment that starts at line 1.

Embedded SQL
------------

``EMBEDDED_EXTRACTORS`` maps a file suffix to a function
``(text: str) -> Extraction``. Registered here: ``.py``, ``.ts``, ``.tsx``,
``.js``, ``.jsx``, ``.cs``, and ``.java``. Each language scanner
(``sql_literals``, ``sql_literals_c``) lists the string literals of the file,
never comments. A literal is kept only when ``sql_shape.is_sql_shaped`` accepts
it: it must start with a SQL verb and the structure that verb needs, so prose
such as "Select an option from the list" is not SQL.

A kept literal that is concatenated (``"..." + x``) or interpolated (f-string,
template ``${}``, C# ``$""``) cannot be scanned as written. It adds one to
``Extraction.skipped`` and still counts as SQL present. Every other kept literal
becomes a ``Fragment`` with origin ``embedded``. Its ``line_offset`` is the
line where the text after the opening quote starts, minus one, so a finding in
a multi-line literal lands on the line of the keyword.

Registered suffixes are scanned automatically and count toward the gate.

Stdlib-only. Python 3.10+.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

import sql_literals
import sql_literals_c
from sql_shape import is_sql_shaped

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


def extraction_of(literals: Iterable[sql_literals.Literal]) -> Extraction:
    """Fragments and the skipped count for the SQL-shaped literals."""
    fragments: list[Fragment] = []
    skipped = 0
    for lit in literals:
        if not is_sql_shaped(lit.text):
            continue
        if lit.concatenated or lit.interpolated:
            skipped += 1
        else:
            fragments.append(Fragment(lit.text, lit.line - 1, ORIGIN_EMBEDDED))
    return Extraction(tuple(fragments), skipped)


def _extractor(
    scan: Callable[[str], list[sql_literals.Literal]],
) -> Callable[[str], Extraction]:
    return lambda text: extraction_of(scan(text))


#: suffix -> extractor.
EMBEDDED_EXTRACTORS: dict[str, Callable[[str], Extraction]] = {
    ".py": _extractor(sql_literals.python_literals),
    **dict.fromkeys(
        (".ts", ".tsx", ".js", ".jsx"), _extractor(sql_literals_c.js_literals)
    ),
    ".cs": _extractor(sql_literals_c.csharp_literals),
    ".java": _extractor(sql_literals_c.java_literals),
}


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
