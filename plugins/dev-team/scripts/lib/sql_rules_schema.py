"""Schema-coupling rules: queries that depend on column count or order.

Stdlib-only. Python 3.10+.
"""

from __future__ import annotations

from collections.abc import Iterator

from sql_rules import OWNER_SCRIPT, Context, Fixture, Hit, Rule
from sql_tokenize import NUMBER, PUNCT, QUOTED, WORD

POSITIONAL_INSERT = "sql.schema.positional-insert"
INSERT_SELECT_STAR = "sql.schema.insert-select-star"
SELECT_STAR = "sql.schema.select-star"
ORDINAL_REFERENCE = "sql.schema.ordinal-reference"

#: Words that end a SELECT list at paren depth 0.
_SELECT_LIST_END = frozenset(
    [
        "FROM",
        "INTO",
        "WHERE",
        "GROUP",
        "HAVING",
        "ORDER",
        "LIMIT",
        "UNION",
        "INTERSECT",
        "EXCEPT",
    ]
)
#: Words that end an ORDER BY / GROUP BY list at paren depth 0.
_BY_LIST_END = frozenset(
    [
        "HAVING",
        "ORDER",
        "LIMIT",
        "OFFSET",
        "FETCH",
        "UNION",
        "INTERSECT",
        "EXCEPT",
        "FOR",
        "WINDOW",
        "OPTION",
        "WITH",
        "INTO",
    ]
)
_SORT_SUFFIX = frozenset(["ASC", "DESC", "NULLS", "FIRST", "LAST"])


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
    while i + 1 < n and tokens[i].kind == PUNCT and tokens[i].text == ".":
        j = i + 1
        while j < n and tokens[j].kind == PUNCT and tokens[j].text == ".":
            j += 1  # T-SQL omitted schema part, as in db..t
        if j >= n or tokens[j].kind not in (WORD, QUOTED):
            break
        i = j + 1
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


def _punct(token, char: str) -> bool:
    return token.kind == PUNCT and token.text == char


def _skip_group(tokens, i: int) -> int:
    """Index after the parenthesized group that opens at ``i``."""
    depth = 0
    n = len(tokens)
    while i < n:
        if _punct(tokens[i], "("):
            depth += 1
        elif _punct(tokens[i], ")"):
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


def _list_start(tokens, s: int) -> int:
    """Index of the first select-list token after ``SELECT`` at ``s``.

    Skips ``DISTINCT [ON (...)]``, ``ALL``, and ``TOP n [PERCENT] [WITH TIES]``.
    """
    n = len(tokens)
    i = s + 1
    while i < n:
        token = tokens[i]
        if _is(token, "DISTINCT") or _is(token, "ALL"):
            i += 1
            if i < n and _is(tokens[i], "ON") and i + 1 < n:
                i = _skip_group(tokens, i + 1)
        elif _is(token, "TOP") and i + 1 < n:
            i = _skip_group(tokens, i + 1) if _punct(tokens[i + 1], "(") else i + 2
            if i < n and _is(tokens[i], "PERCENT"):
                i += 1
            if i + 1 < n and _is(tokens[i], "WITH") and _is(tokens[i + 1], "TIES"):
                i += 2
        else:
            break
    return i


def _split_items(tokens, start: int, ends: frozenset) -> list[list]:
    """Comma-separated items from ``start`` to the first depth-0 end marker."""
    items: list[list] = [[]]
    depth = 0
    for token in tokens[start:]:
        if _punct(token, "("):
            depth += 1
        elif _punct(token, ")"):
            depth -= 1
            if depth < 0:
                break
        elif depth == 0:
            if _punct(token, ";") or (
                token.kind == WORD and token.text.upper() in ends
            ):
                break
            if _punct(token, ","):
                items.append([])
                continue
        items[-1].append(token)
    return [item for item in items if item]


def _is_star_item(item) -> bool:
    """``*`` or ``name[.name...].*``, and nothing else."""
    if not _punct(item[-1], "*"):
        return False
    if len(item) == 1:
        return True
    body = item[:-1]
    # Strictly name ( . name )* . -- so ``2 * 3`` and ``ON db.*`` do not match.
    if len(body) % 2 != 0:
        return False
    for k, token in enumerate(body):
        if k % 2 == 0 and token.kind not in (WORD, QUOTED):
            return False
        if k % 2 == 1 and not _punct(token, "."):
            return False
    return True


def _is_exists_subquery(tokens, s: int) -> bool:
    """``EXISTS (SELECT ...)``: the star there never reaches the caller."""
    return s >= 2 and _punct(tokens[s - 1], "(") and _is(tokens[s - 2], "EXISTS")


def _star_item(tokens, s: int):
    """The first ``*`` or ``t.*`` item of the SELECT at ``s``, or ``None``."""
    items = _split_items(tokens, _list_start(tokens, s), _SELECT_LIST_END)
    return next((item for item in items if _is_star_item(item)), None)


def _insert_sources(tokens) -> dict[int, list[int]]:
    """Map each ``INSERT`` index to the SELECTs that supply its rows.

    The sources are the SELECTs at the statement's own depth after the target
    and optional column list, so ``UNION`` branches count and a subquery in a
    ``VALUES`` row or a ``FROM`` clause does not.
    """
    n = len(tokens)
    found: dict[int, list[int]] = {}
    for i, token in enumerate(tokens):
        if not _is(token, "INSERT"):
            continue
        j = i + 1
        if j < n and _is(tokens[j], "INTO"):
            j += 1
        j = _name_end(tokens, j)
        if (
            j < n
            and _punct(tokens[j], "(")
            and not (j + 1 < n and _is(tokens[j + 1], "SELECT"))
        ):
            j = _skip_group(tokens, j)  # the column list
        base = None
        depth = 0
        sources: list[int] = []
        for k in range(j, n):
            t = tokens[k]
            if _punct(t, ";"):
                break
            if _punct(t, "("):
                depth += 1
            elif _punct(t, ")"):
                depth -= 1
                if depth < 0:
                    break
            elif _is(t, "VALUES") and depth == 0 and base is None:
                break
            elif _is(t, "SELECT"):
                if base is None and (
                    depth == 0 or (depth == 1 and _punct(tokens[k - 1], "("))
                ):
                    base = depth
                if depth == base:
                    sources.append(k)
        if sources:
            found[i] = sources
    return found


def check_insert_select_star(ctx: Context) -> Iterator[Hit]:
    """``INSERT ... SELECT *`` copies whatever columns the source has."""
    tokens = ctx.tokens
    for i, sources in _insert_sources(tokens).items():
        for s in sources:
            star = _star_item(tokens, s)
            if star:
                yield Hit(tokens[i].line, _render([*tokens[i : sources[0] + 1], *star]))
                break


def check_select_star(ctx: Context) -> Iterator[Hit]:
    """``SELECT *`` or ``SELECT t.*`` outside ``EXISTS`` and ``INSERT ... SELECT``."""
    tokens = ctx.tokens
    insert_selects = {s for srcs in _insert_sources(tokens).values() for s in srcs}
    for s, token in enumerate(tokens):
        if not _is(token, "SELECT") or s in insert_selects:
            continue
        if _is_exists_subquery(tokens, s):
            continue
        star = _star_item(tokens, s)
        if star:
            yield Hit(token.line, _render([token, *star]))


def _enclosing_open(tokens, k: int) -> int | None:
    """Index of the ``(`` that encloses token ``k``, or ``None`` at depth 0."""
    depth = 0
    for i in range(k - 1, -1, -1):
        if _punct(tokens[i], ")"):
            depth += 1
        elif _punct(tokens[i], "("):
            if depth == 0:
                return i
            depth -= 1
    return None


def _in_query_scope(tokens, k: int) -> bool:
    """True at statement level or inside a parenthesized query.

    ``OVER (ORDER BY a)``, ``WITHIN GROUP (ORDER BY a)``, and aggregate
    ``ORDER BY`` sort a function's input, not the result set.
    """
    opener = _enclosing_open(tokens, k)
    if opener is None:
        return True
    nxt = tokens[opener + 1] if opener + 1 < len(tokens) else None
    return nxt is not None and (
        _is(nxt, "SELECT") or _is(nxt, "WITH") or _punct(nxt, "(")
    )


def _is_ordinal(item) -> bool:
    while (
        len(item) > 1
        and item[-1].kind == WORD
        and item[-1].text.upper() in _SORT_SUFFIX
    ):
        item = item[:-1]
    return len(item) == 1 and item[0].kind == NUMBER and item[0].text.isdigit()


def check_ordinal_reference(ctx: Context) -> Iterator[Hit]:
    """``ORDER BY 2`` or ``GROUP BY 1`` names a select-list position."""
    tokens = ctx.tokens
    n = len(tokens)
    for k, token in enumerate(tokens):
        if not (_is(token, "ORDER") or _is(token, "GROUP")):
            continue
        if k + 1 >= n or not _is(tokens[k + 1], "BY"):
            continue
        if not _in_query_scope(tokens, k):
            continue
        items = _split_items(tokens, k + 2, _BY_LIST_END)
        if any(_is_ordinal(item) for item in items):
            shown = [t for item in items[:3] for t in item]
            yield Hit(token.line, _render(tokens[k : k + 2] + shown))


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
    Rule(
        id=INSERT_SELECT_STAR,
        family="schema",
        dialect="ansi",
        owner=OWNER_SCRIPT,
        severity="warning",
        message="INSERT ... SELECT * copies whatever columns the source has and breaks when either table changes.",
        fix="List the source columns in the SELECT and the target columns in the INSERT.",
        positive=(
            Fixture("no-column-list", "INSERT INTO archive SELECT * FROM orders", (1,)),
            Fixture(
                "with-column-list",
                "INSERT INTO a (x, y) SELECT * FROM b;",
                (1,),
            ),
            Fixture("qualified-star", "insert into a select o.* from orders o;", (1,)),
            Fixture(
                "second-statement",
                "SELECT 1;\nINSERT INTO a\nSELECT * FROM b;",
                (2,),
            ),
            Fixture(
                "union-branch",
                "INSERT INTO a SELECT x FROM b UNION ALL SELECT * FROM c;",
                (1,),
            ),
        ),
        negative=(
            Fixture("named-columns", "INSERT INTO a (x) SELECT x FROM b;"),
            Fixture("named-without-target-list", "INSERT INTO a SELECT x, y FROM b;"),
            Fixture("values-row", "INSERT INTO a (x) VALUES (1);"),
            Fixture("star-in-count", "INSERT INTO a (n) SELECT COUNT(*) FROM b;"),
            Fixture("plain-select-star", "SELECT * FROM b;"),
            Fixture("in-comment", "-- INSERT INTO a SELECT * FROM b"),
        ),
        check=check_insert_select_star,
    ),
    Rule(
        id=SELECT_STAR,
        family="schema",
        dialect="ansi",
        owner=OWNER_SCRIPT,
        severity="warning",
        message="SELECT * returns whatever columns exist, so a column added or reordered changes the result shape.",
        fix="List the columns the caller needs: SELECT id, name FROM t.",
        positive=(
            Fixture("bare-star", "SELECT * FROM orders", (1,)),
            Fixture("qualified-star", "SELECT o.* FROM orders o", (1,)),
            Fixture("distinct-star", "SELECT DISTINCT * FROM orders;", (1,)),
            Fixture("top-star", "SELECT TOP 10 * FROM orders;", (1,)),
            Fixture("star-among-columns", "SELECT id, o.* FROM orders o;", (1,)),
            Fixture("view-body", "CREATE VIEW v AS\nSELECT * FROM t;", (2,)),
            Fixture(
                "derived-table",
                "SELECT id FROM (SELECT * FROM t) s;",
                (1,),
            ),
        ),
        negative=(
            Fixture("count-star", "SELECT COUNT(*) FROM orders"),
            Fixture(
                "exists-subquery", "SELECT id FROM t WHERE EXISTS (SELECT * FROM u)"
            ),
            Fixture(
                "not-exists-subquery",
                "SELECT id FROM t WHERE NOT EXISTS (SELECT * FROM u);",
            ),
            Fixture("multiplication", "SELECT price * qty FROM lines;"),
            Fixture("named-columns", "SELECT id, name FROM orders;"),
            Fixture("insert-select-star", "INSERT INTO archive SELECT * FROM orders"),
            Fixture("grant-on-schema", "GRANT SELECT ON db.* TO reader;"),
            Fixture("in-comment", "-- SELECT * FROM orders"),
        ),
        check=check_select_star,
    ),
    Rule(
        id=ORDINAL_REFERENCE,
        family="schema",
        dialect="ansi",
        owner=OWNER_SCRIPT,
        severity="warning",
        message="ORDER BY or GROUP BY a column number breaks silently when the select list is reordered.",
        fix="Name the column or its alias: ORDER BY created_at.",
        positive=(
            Fixture("order-by-ordinal", "SELECT a, b FROM t ORDER BY 2", (1,)),
            Fixture("group-by-ordinal", "SELECT a, COUNT(*) FROM t GROUP BY 1", (1,)),
            Fixture("ordinal-with-direction", "SELECT a FROM t ORDER BY 1 DESC;", (1,)),
            Fixture(
                "mixed-list",
                "SELECT a, b FROM t\nORDER BY a, 2;",
                (2,),
            ),
            Fixture(
                "subquery",
                "SELECT x FROM (SELECT a x FROM t ORDER BY 1) s;",
                (1,),
            ),
        ),
        negative=(
            Fixture("column-name", "SELECT a FROM t ORDER BY created_at"),
            Fixture("window-order", "SELECT ROW_NUMBER() OVER (ORDER BY a) FROM t"),
            Fixture(
                "window-ordinal",
                "SELECT ROW_NUMBER() OVER (PARTITION BY b ORDER BY 1) FROM t;",
            ),
            Fixture("aggregate-order", "SELECT STRING_AGG(a, ',' ORDER BY 1) FROM t;"),
            Fixture("expression", "SELECT a FROM t ORDER BY a + 1;"),
            Fixture("parameter", "SELECT a FROM t ORDER BY $1;"),
            Fixture("in-comment", "-- SELECT a FROM t ORDER BY 2"),
        ),
        check=check_ordinal_reference,
    ),
)
