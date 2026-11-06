"""SQL dialect model for the SQL anti-pattern detector.

A rule declares one dialect tag. ``ansi`` rules fire on every file. A
``tsql`` or ``postgres`` rule fires only when the file's dialect equals its
tag. The file dialect comes from ``--dialect`` or from ``infer_dialect``.

``infer_dialect`` is a stub in the first slice and always answers ``ansi``.
A later slice replaces its body with real inference. Callers depend on the
signature, not on the answer.

Stdlib-only. Python 3.10+.
"""

from __future__ import annotations

ANSI = "ansi"
TSQL = "tsql"
POSTGRES = "postgres"

DIALECTS = (ANSI, TSQL, POSTGRES)
DEFAULT_DIALECT = ANSI


def normalize_dialect(name: str) -> str:
    """Return the canonical dialect name, or raise ``ValueError``."""
    value = name.strip().lower()
    if value not in DIALECTS:
        raise ValueError(
            f"unknown dialect {name!r}; expected one of {', '.join(DIALECTS)}"
        )
    return value


def infer_dialect(path: str, text: str) -> str:
    """Return the dialect of one file. First slice: always ``ansi``."""
    return DEFAULT_DIALECT


def rule_applies(rule_dialect: str, file_dialect: str) -> bool:
    """True when a rule tagged ``rule_dialect`` runs on a ``file_dialect`` file."""
    return rule_dialect == ANSI or rule_dialect == file_dialect
