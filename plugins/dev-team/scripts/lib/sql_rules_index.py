"""Index-defeating rules: predicates that stop the database using an index.

``function-on-column`` and ``leading-wildcard`` are script-owned.
``implicit-conversion`` needs the column type from a ``CREATE TABLE`` and is
agent-owned: it has no ``check``.

Stdlib-only. Python 3.10+.
"""

from __future__ import annotations

from collections.abc import Iterator

from sql_clauses import (
    is_punct,
    is_statement_start,
    matching_parens,
    render,
    segments,
    word,
)
from sql_rules import OWNER_AGENT, OWNER_SCRIPT, Context, Fixture, Hit, Rule
from sql_tokenize import QUOTED, STRING, WORD

FUNCTION_ON_COLUMN = "sql.index.function-on-column"
LEADING_WILDCARD = "sql.index.leading-wildcard"
IMPLICIT_CONVERSION = "sql.index.implicit-conversion"

_CLAUSE_END = frozenset(
    {
        "GROUP",
        "HAVING",
        "ORDER",
        "LIMIT",
        "OFFSET",
        "FETCH",
        "UNION",
        "INTERSECT",
        "EXCEPT",
        "WINDOW",
        "RETURNING",
        "FOR",
        "OPTION",
        "QUALIFY",
        "MINUS",
        # upsert tails: INSERT ... WHERE ... ON CONFLICT (a) DO UPDATE SET ...
        "ON",
        "CONFLICT",
        "DUPLICATE",
        "DO",
        "SET",
    }
)
_ON_END = _CLAUSE_END | frozenset(
    {"WHERE", "JOIN", "INNER", "LEFT", "RIGHT", "FULL", "CROSS", "NATURAL", "OUTER"}
)

# Words before "(" that are syntax, not a function call.
_NOT_A_FUNCTION = frozenset(
    {
        "IN",
        "EXISTS",
        "ANY",
        "ALL",
        "SOME",
        "AND",
        "OR",
        "NOT",
        "WHERE",
        "ON",
        "AS",
        "CASE",
        "WHEN",
        "THEN",
        "ELSE",
        "END",
        "BETWEEN",
        "LIKE",
        "ILIKE",
        "IS",
        "USING",
        "OVER",
        "FILTER",
        "VALUES",
        "SELECT",
        "FROM",
        "JOIN",
        "ROW",
        "INTERVAL",
        "DISTINCT",
        "WITH",
    }
)
_AGGREGATES = frozenset(
    {"COUNT", "SUM", "AVG", "MIN", "MAX", "STDDEV", "VARIANCE", "STRING_AGG"}
)
# Functions that a full-text index serves: not reported.
_INDEXABLE_FUNCTIONS = frozenset({"CONTAINS", "FREETEXT", "MATCH", "AGAINST"})
# Words inside a call that are not column references.
_NOT_A_COLUMN = frozenset(
    {
        "NULL",
        "TRUE",
        "FALSE",
        "FROM",
        "FOR",
        "BOTH",
        "LEADING",
        "TRAILING",
        "INTERVAL",
        "DISTINCT",
        "ALL",
        "CASE",
        "WHEN",
        "THEN",
        "ELSE",
        "END",
        "AND",
        "OR",
        "NOT",
        "IS",
        "IN",
        "LIKE",
        "CURRENT_DATE",
        "CURRENT_TIME",
        "CURRENT_TIMESTAMP",
        "CURRENT_USER",
        "YEAR",
        "QUARTER",
        "MONTH",
        "WEEK",
        "DAY",
        "HOUR",
        "MINUTE",
        "SECOND",
        "MILLISECOND",
        "MICROSECOND",
        "EPOCH",
        "DOW",
        "DOY",
    }
)


# Functions whose first argument is a type or a date part, not a column.
_FIRST_ARGUMENT_IS_NOT_A_COLUMN = frozenset(
    {
        "CONVERT",
        "TRY_CONVERT",
        "DATEADD",
        "DATEDIFF",
        "DATEDIFF_BIG",
        "DATEPART",
        "DATENAME",
    }
)
# Words that continue a type name: DOUBLE PRECISION, TIMESTAMP WITH TIME ZONE.
_TYPE_TAIL = frozenset(
    {"PRECISION", "VARYING", "WITH", "WITHOUT", "TIME", "ZONE", "UNSIGNED", "SIGNED"}
)


def _skip_type(tokens, pairs: dict[int, int], i: int, end: int) -> int:
    """Index after the type name that starts at ``i``, with its length and tail."""
    if i < end and tokens[i].kind in (WORD, QUOTED):
        i += 1
    while i < end:
        if is_punct(tokens[i], "(") and i in pairs:
            i = pairs[i] + 1
        elif word(tokens[i]) in _TYPE_TAIL:
            i += 1
        else:
            break
    return i


def _has_column(tokens, pairs: dict[int, int], start: int, end: int) -> bool:
    """True when ``tokens[start:end]`` names a column, not only literals."""
    i = start
    while i < end:
        token = tokens[i]
        name = word(token)
        if name == "AS":
            i = _skip_type(tokens, pairs, i + 1, end)
            continue
        if (
            name in _FIRST_ARGUMENT_IS_NOT_A_COLUMN
            and i + 1 < end
            and is_punct(tokens[i + 1], "(")
        ):
            j = i + 2  # skip the type or date part, up to the first comma
            while j < end and not is_punct(tokens[j], ","):
                j = pairs[j] + 1 if j in pairs and is_punct(tokens[j], "(") else j + 1
            i = j + 1
            continue
        if token.kind in (WORD, QUOTED):
            called = i + 1 < end and is_punct(tokens[i + 1], "(")
            variable = token.text[:1] in "@:$"
            cast = i > start and is_punct(tokens[i - 1], ":")
            if (
                not called
                and not variable
                and not cast
                and word(token) not in _NOT_A_COLUMN
            ):
                return True
        i += 1
    return False


def _predicate_regions(tokens, items: list[int]) -> Iterator[tuple[int, int]]:
    """Token index ranges of each ``WHERE`` and join ``ON`` clause in one segment."""
    names = [word(tokens[i]) for i in items]
    for position, name in enumerate(names):
        if name == "WHERE":
            ends = _CLAUSE_END
        elif name == "ON" and "JOIN" in names[:position]:
            ends = _ON_END
        else:
            continue
        end = len(items)
        for later in range(position + 1, len(items)):
            if (
                names[later] in ends
                or is_statement_start(tokens, items, later)
                or (name == "ON" and is_punct(tokens[items[later]], ","))
            ):
                end = later
                break
        if position + 1 < end:
            stop = items[end] if end < len(items) else items[-1] + 1
            yield items[position + 1], stop


def check_function_on_column(ctx: Context) -> Iterator[Hit]:
    """A function over a column in ``WHERE`` or ``ON`` hides the column from its index."""
    tokens = ctx.tokens
    pairs = matching_parens(tokens)
    for items in segments(tokens):
        for start, stop in _predicate_regions(tokens, items):
            i = start
            while i < stop:
                token = tokens[i]
                if (
                    is_punct(token, "(")
                    and i in pairs
                    and word(tokens[i + 1]) in ("SELECT", "WITH")
                ):
                    i = pairs[i] + 1  # a subquery is its own segment
                    continue
                called = (
                    token.kind == WORD
                    and i + 1 < stop
                    and is_punct(tokens[i + 1], "(")
                    and (i + 1) in pairs
                    and token.text.upper() not in _NOT_A_FUNCTION
                )
                if not called:
                    i += 1
                    continue
                close = pairs[i + 1]
                name = token.text.upper()
                skip = name in _AGGREGATES or name in _INDEXABLE_FUNCTIONS
                if not skip and _has_column(tokens, pairs, i, close + 1):
                    yield Hit(token.line, render(tokens[i : close + 1]))
                i = close + 1


# --- leading-wildcard ------------------------------------------------------

_LIKE_WORDS = frozenset({"LIKE", "ILIKE"})
_STRING_PREFIXES = frozenset({"N", "E"})


def check_leading_wildcard(ctx: Context) -> Iterator[Hit]:
    """``LIKE '%x'`` cannot use a B-tree index: it has no fixed prefix to seek."""
    tokens = ctx.tokens
    n = len(tokens)
    for i, token in enumerate(tokens):
        if word(token) not in _LIKE_WORDS or i + 1 >= n:
            continue
        j = i + 1
        if word(tokens[j]) in _STRING_PREFIXES and j + 1 < n:
            j += 1
        if word(tokens[j]) == "CONCAT" and j + 2 < n and is_punct(tokens[j + 1], "("):
            j += 2
        pattern = tokens[j]
        if pattern.kind == STRING and pattern.text[1:2] == "%":
            yield Hit(token.line, render(tokens[max(i - 1, 0) : j + 1]))


RULES = (
    Rule(
        id=FUNCTION_ON_COLUMN,
        family="index",
        dialect="ansi",
        owner=OWNER_SCRIPT,
        severity="warning",
        message="A function over a column in WHERE or ON stops the database using a plain index on that column.",
        fix="Compare the bare column to a transformed value, or create an expression index on the function.",
        positive=(
            Fixture(
                "lower-in-where",
                "SELECT id FROM users WHERE LOWER(email) = 'a@b.c'",
                (1,),
            ),
            Fixture("upper-in-on", "SELECT a FROM t JOIN u ON UPPER(t.c) = u.c", (1,)),
            Fixture("cast", "SELECT 1 FROM t WHERE CAST(code AS int) = 5", (1,)),
            Fixture(
                "date-part",
                "SELECT 1 FROM t WHERE DATE(created_at) = '2024-01-01'",
                (1,),
            ),
            Fixture(
                "nested-in-parens",
                "SELECT 1 FROM t WHERE a = 1 AND (COALESCE(b, 0) = 2 OR c = 3)",
                (1,),
            ),
            Fixture(
                "second-line",
                "SELECT 1 FROM t\nWHERE a = 1\n  AND TRIM(b) = 'x'",
                (3,),
            ),
            Fixture("update-where", "UPDATE t SET a = 1 WHERE LOWER(b) = 'x'", (1,)),
        ),
        negative=(
            Fixture(
                "function-over-literal",
                "SELECT id FROM users WHERE email = LOWER('A@B.C')",
            ),
            Fixture("in-list", "SELECT id FROM t WHERE id IN (1, 2)"),
            Fixture("exists", "SELECT id FROM t WHERE EXISTS (SELECT 1 FROM u)"),
            Fixture(
                "having-aggregate", "SELECT a FROM t GROUP BY a HAVING COUNT(*) > 1"
            ),
            Fixture(
                "select-list-function", "SELECT LOWER(email) FROM users WHERE id = 1"
            ),
            Fixture("now", "SELECT 1 FROM t WHERE created_at > NOW()"),
            Fixture(
                "extract-literal", "SELECT 1 FROM t WHERE y = EXTRACT(year FROM NOW())"
            ),
            Fixture("cast-literal", "SELECT 1 FROM t WHERE a = CAST('5' AS int)"),
            Fixture("variable-argument", "SELECT 1 FROM t WHERE a = LOWER(@name)"),
            Fixture("expression-index", "CREATE INDEX i ON t (LOWER(email))"),
            Fixture(
                "fk-action", "CREATE TABLE c (p int REFERENCES p ON DELETE CASCADE)"
            ),
            Fixture(
                "subquery-select-list",
                "SELECT 1 FROM t WHERE id IN (SELECT LOWER(x) FROM u)",
            ),
            Fixture("full-text", "SELECT 1 FROM t WHERE CONTAINS(body, 'x')"),
        ),
        check=check_function_on_column,
    ),
    Rule(
        id=LEADING_WILDCARD,
        family="index",
        dialect="ansi",
        owner=OWNER_SCRIPT,
        severity="warning",
        message="LIKE with a leading % has no fixed prefix, so the database scans the whole table or index.",
        fix="Match a prefix (LIKE 'abc%'), or use full-text or trigram search for contains-style matching.",
        positive=(
            Fixture("like", "SELECT id FROM t WHERE name LIKE '%smith'", (1,)),
            Fixture("contains", "SELECT id FROM t WHERE name LIKE '%smith%'", (1,)),
            Fixture("not-like", "SELECT id FROM t WHERE name NOT LIKE '%smith'", (1,)),
            Fixture("ilike", "SELECT id FROM t WHERE name ILIKE '%smith'", (1,)),
            Fixture(
                "tsql-national", "SELECT id FROM t WHERE name LIKE N'%smith'", (1,)
            ),
            Fixture("concat", "SELECT id FROM t WHERE name LIKE CONCAT('%', @q)", (1,)),
            Fixture("second-line", "SELECT id FROM t\nWHERE name LIKE '%x'", (2,)),
        ),
        negative=(
            Fixture("prefix", "SELECT id FROM t WHERE name LIKE 'smith%'"),
            Fixture("no-wildcard", "SELECT id FROM t WHERE name LIKE 'smith'"),
            Fixture("parameter", "SELECT id FROM t WHERE name LIKE @pattern"),
            Fixture("create-table-like", "CREATE TABLE a (LIKE b)"),
            Fixture("percent-not-leading", "SELECT id FROM t WHERE name LIKE 'a%b'"),
            Fixture("in-string", "SELECT 'name LIKE ''%x'''"),
        ),
        check=check_leading_wildcard,
    ),
    Rule(
        id=IMPLICIT_CONVERSION,
        family="index",
        dialect="ansi",
        owner=OWNER_AGENT,
        severity="warning",
        message="Comparing a character column to a number makes the database convert the column, which stops index use.",
        fix="Compare to a literal of the column type, for example code = '42'.",
        positive=("sql-index-implicit-conversion.sql",),
        negative=("sql-index-int-compare.sql",),
    ),
)
