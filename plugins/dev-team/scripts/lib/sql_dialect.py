"""SQL dialect model for the SQL anti-pattern detector.

A rule declares one dialect tag. ``ansi`` rules fire on every file. A
``tsql`` or ``postgres`` rule fires only when the file's dialect equals its
tag. The file dialect comes from ``--dialect`` or from ``infer_dialect``.

``infer_dialect`` reads dialect markers from the file text (the tables
below). Markers in comments and string literals do not count. Evidence for
one dialect gives that dialect. No evidence, or evidence for both, gives
``ansi``.

Stdlib-only. Python 3.10+.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from sql_tokenize import COMMENT, NUMBER, PUNCT, QUOTED, STRING, WORD, Token, tokenize

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


#: Bare keywords that only one dialect uses. Uppercase.
KEYWORD_MARKERS = {
    TSQL: frozenset({"NOLOCK", "NVARCHAR"}),
    POSTGRES: frozenset({"RETURNING", "ILIKE", "SERIAL", "CONCURRENTLY"}),
}

#: ``[ident]`` that is a T-SQL quoted identifier, not a Postgres subscript.
_BRACKET_IDENT = re.compile(r"^\[[A-Za-z_][\w ]*\]$")


def is_batch_separator(tokens: Sequence[Token], i: int) -> bool:
    """True when ``tokens[i]`` is a ``GO`` that stands alone on its line."""
    token = tokens[i]
    if token.kind != WORD or token.text.upper() != "GO":
        return False
    before = tokens[i - 1].line if i > 0 else 0
    after = tokens[i + 1].line if i + 1 < len(tokens) else 0
    return before != token.line and after != token.line


def _adjacent(prev: Token, token: Token) -> bool:
    return prev.line == token.line and prev.col + len(prev.text) == token.col


def _is_top(tokens: Sequence[Token], i: int) -> bool:
    """``TOP 5`` or ``TOP (5)``."""
    if tokens[i].kind != WORD or tokens[i].text.upper() != "TOP":
        return False
    if i + 1 >= len(tokens):
        return False
    nxt = tokens[i + 1]
    return nxt.kind == NUMBER or (nxt.kind == PUNCT and nxt.text == "(")


def _is_bracket_ident(tokens: Sequence[Token], i: int) -> bool:
    token = tokens[i]
    if token.kind != QUOTED or not _BRACKET_IDENT.match(token.text):
        return False
    if i == 0:
        return True
    prev = tokens[i - 1]
    subscript = prev.kind in (WORD, QUOTED) or prev.text == ")"
    return not (subscript and _adjacent(prev, token))


def _is_cast(tokens: Sequence[Token], i: int) -> bool:
    """``::`` as two adjacent colons."""
    if tokens[i].kind != PUNCT or tokens[i].text != ":" or i + 1 >= len(tokens):
        return False
    nxt = tokens[i + 1]
    return nxt.kind == PUNCT and nxt.text == ":" and _adjacent(tokens[i], nxt)


def _is_dollar_quote(tokens: Sequence[Token], i: int) -> bool:
    return tokens[i].kind == STRING and tokens[i].text.startswith("$")


#: Structural markers: ``(dialect, test(tokens, i))``. A test sees the
#: non-comment tokens and the index of the token it judges.
STRUCTURAL_MARKERS = (
    (TSQL, is_batch_separator),
    (TSQL, _is_top),
    (TSQL, _is_bracket_ident),
    (POSTGRES, _is_cast),
    (POSTGRES, _is_dollar_quote),
)


def infer_dialect(path: str, text: str) -> str:
    """Return the dialect of one file from its markers.

    ``path`` is unused today and kept in the signature for callers.
    """
    tokens = [t for t in tokenize(text) if t.kind != COMMENT]
    found: set[str] = set()
    for i, token in enumerate(tokens):
        if token.kind == WORD:
            word = token.text.upper()
            for dialect, words in KEYWORD_MARKERS.items():
                if word in words:
                    found.add(dialect)
        for dialect, test in STRUCTURAL_MARKERS:
            if test(tokens, i):
                found.add(dialect)
    if len(found) == 1:
        return found.pop()
    return DEFAULT_DIALECT


def rule_applies(rule_dialect: str, file_dialect: str) -> bool:
    """True when a rule tagged ``rule_dialect`` runs on a ``file_dialect`` file."""
    return rule_dialect == ANSI or rule_dialect == file_dialect
