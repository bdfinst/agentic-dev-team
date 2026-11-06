"""Decide whether a string literal is SQL-shaped.

A literal is SQL-shaped when, after leading whitespace and SQL comments, it
starts with a statement verb and the structure that verb needs:

- ``INSERT [IGNORE|OR x] INTO <table>`` then ``(``, ``VALUES``, ``SELECT``,
  ``DEFAULT``, or ``OVERRIDING``
- ``SELECT [DISTINCT|TOP n] <list> FROM <source>``, where ``<list>`` is
  comma-separated names, ``*``, calls, numbers, strings, or placeholders
- ``UPDATE <table> SET <column> =``
- ``DELETE FROM <source>``
- ``WITH [RECURSIVE] <name> [(cols)] AS (``
- ``ALTER TABLE <table>`` then an alter action (``ADD``, ``DROP``, ...)
- ``CREATE [modifiers] TABLE|INDEX|VIEW <name>`` with its follow-on keyword

``<source>`` must be followed by the end of the text, ``;``, ``,``, ``)``, or
a clause keyword (``WHERE``, ``JOIN``, ``ORDER``, ...), so that prose such as
"Select an option from the list" does not match. Two words after a verb with
no comma, ``AS``, or keyword between them are prose, not a select list.

Not SQL-shaped, on purpose: ``SELECT`` with an arithmetic or ``CASE`` select
list, ``SELECT`` without ``FROM``, and statements split across concatenated
literals. A missed literal costs one hit; a prose match would cost trust.

Stdlib-only. Python 3.10+.
"""

from __future__ import annotations

import re

_NAME = r'(?:[\w$#@]+|"[^"\n]+"|`[^`\n]+`|\[[^\]\n]+\]|\$?\{[^{}\n]*\}|%s)'
_QNAME = rf"{_NAME}(?:\s*\.\s*{_NAME})*"
_CALL = r"\s*\((?:[^()]|\((?:[^()]|\([^()]*\))*\))*\)"
_ITEM = (
    rf"(?:{_QNAME}(?:\.\*)?(?:{_CALL})?|\*|\?|:\w+|\d+(?:\.\d+)?|'[^'\n]*')"
    rf"(?:\s+AS\s+{_NAME})?"
)
_KW = (
    r"(?:WHERE|JOIN|INNER|LEFT|RIGHT|FULL|CROSS|NATURAL|ORDER|GROUP|HAVING|LIMIT|"
    r"OFFSET|FETCH|UNION|INTERSECT|EXCEPT|ON|USING|FOR|WINDOW|RETURNING|OUTPUT)"
)
_TAIL = (
    rf"(?:\s+AS\s+{_NAME}|\s+(?!{_KW}\b){_NAME}(?=\s+{_KW}\b))?"
    rf"(?:\s*(?:[;,)]|\Z)|\s+{_KW}\b)"
)
_SOURCE = rf"(?:{_QNAME}{_TAIL}|\(\s*(?:SELECT|WITH)\b)"

_PREFIX = r"(?:\s|--[^\n]*(?:\n|\Z)|/\*[\s\S]*?\*/)*"

_INSERT = (
    rf"INSERT\s+(?:IGNORE\s+|OR\s+\w+\s+)?INTO\s+{_QNAME}\s*"
    r"(?:\(|(?:VALUES?|SELECT|DEFAULT|OVERRIDING)\b)"
)
_SELECT = (
    rf"SELECT\s+(?:(?:DISTINCT|ALL)\s+|TOP\s*\(?\d+\)?\s+)?{_ITEM}"
    rf"(?:\s*,\s*{_ITEM})*\s+FROM\s+{_SOURCE}"
)
_UPDATE = (
    rf"UPDATE\s+(?:OR\s+\w+\s+)?{_QNAME}(?:\s+(?:AS\s+)?(?!SET\b){_NAME})?"
    rf"\s+SET\s+{_QNAME}\s*="
)
_DELETE = rf"DELETE\s+FROM\s+{_SOURCE}"
_WITH = (
    rf"WITH\s+(?:RECURSIVE\s+)?{_NAME}(?:\s*\([^()\n]*\))?\s+AS\s*"
    r"(?:(?:NOT\s+)?MATERIALIZED\s*)?\("
)
_ALTER = (
    rf"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?{_QNAME}\s+"
    r"(?:ADD|DROP|ALTER|RENAME|MODIFY|CHANGE|SET|ENABLE|DISABLE|OWNER|ATTACH|"
    r"DETACH|VALIDATE|NOCHECK|CHECK|WITH|REPLICA|CLUSTER)\b"
)
_CREATE = (
    r"CREATE\s+(?:OR\s+REPLACE\s+)?"
    r"(?:(?:(?:GLOBAL|LOCAL)\s+)?(?:TEMP|TEMPORARY)\s+|UNLOGGED\s+|UNIQUE\s+|"
    r"CLUSTERED\s+|NONCLUSTERED\s+|MATERIALIZED\s+)*"
    rf"(?:TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?{_QNAME}\s*(?:\(|AS\b|LIKE\b)"
    rf"|INDEX\s+(?:CONCURRENTLY\s+)?(?:IF\s+NOT\s+EXISTS\s+)?{_NAME}\s+ON\b"
    rf"|VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?{_QNAME}\s*(?:\([^()]*\)\s*)?AS\b)"
)
_STATEMENTS = (_INSERT, _SELECT, _UPDATE, _DELETE, _WITH, _ALTER, _CREATE)

SHAPE_RE = re.compile(
    _PREFIX + "(?:" + "|".join(f"(?:{s})" for s in _STATEMENTS) + ")", re.IGNORECASE
)


def is_sql_shaped(text: str) -> bool:
    """True when ``text`` starts like a SQL statement, as defined above."""
    return SHAPE_RE.match(text) is not None
