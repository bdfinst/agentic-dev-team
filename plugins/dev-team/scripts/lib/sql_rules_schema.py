"""Schema-coupling rules: queries that depend on column count or order.

Stdlib-only. Python 3.10+.
"""

from __future__ import annotations

from collections.abc import Iterator

from sql_rules import OWNER_SCRIPT, Context, Fixture, Hit, Rule
from sql_tokenize import PUNCT, QUOTED, WORD

POSITIONAL_INSERT = "sql.schema.positional-insert"


def _is(token, word: str) -> bool:
    return token.kind == WORD and token.text.upper() == word


def _render(tokens) -> str:
    """Matched tokens as one line of text, with dotted names rejoined."""
    return " ".join(t.text for t in tokens).replace(" . ", ".")


def _name_end(tokens, i: int) -> int:
    """Index after a possibly dotted table name starting at ``i``, or ``i``."""
    n = len(tokens)
    if i >= n or tokens[i].kind not in (WORD, QUOTED):
        return i
    i += 1
    while (
        i + 1 < n
        and tokens[i].kind == PUNCT
        and tokens[i].text == "."
        and tokens[i + 1].kind in (WORD, QUOTED)
    ):
        i += 2
    return i


def check_positional_insert(ctx: Context) -> Iterator[Hit]:
    """``INSERT [INTO] <table> [AS alias] VALUES`` has no column list."""
    tokens = ctx.tokens
    n = len(tokens)
    for i, token in enumerate(tokens):
        if not _is(token, "INSERT"):
            continue
        j = i + 1
        if j < n and _is(tokens[j], "INTO"):
            j += 1
        end = _name_end(tokens, j)
        if end == j:
            continue
        j = end
        if j + 1 < n and _is(tokens[j], "AS") and tokens[j + 1].kind in (WORD, QUOTED):
            j += 2
        if j < n and (_is(tokens[j], "VALUES") or _is(tokens[j], "VALUE")):
            yield Hit(token.line, _render(tokens[i : j + 1]))


RULES = (
    Rule(
        id=POSITIONAL_INSERT,
        family="schema",
        dialect="ansi",
        owner=OWNER_SCRIPT,
        severity="warning",
        message="INSERT without a column list depends on column order and breaks when the table gains a column.",
        fix="Name the target columns: INSERT INTO t (col1, col2) VALUES (...).",
        positive=(
            Fixture("single-row", "INSERT INTO orders VALUES (1, 'a');", (1,)),
            Fixture("multi-row-lowercase", "insert into t values (1), (2);", (1,)),
            Fixture("second-statement", "SELECT 1;\nINSERT INTO s.t VALUES (1);", (2,)),
        ),
        negative=(
            Fixture("column-list", "INSERT INTO orders (id, name) VALUES (1, 'a');"),
            Fixture("column-list-no-space", "insert into orders(id) values (1);"),
            Fixture("default-values", "INSERT INTO orders DEFAULT VALUES;"),
            Fixture("in-comment", "-- INSERT INTO t VALUES (1)"),
        ),
        check=check_positional_insert,
    ),
)
