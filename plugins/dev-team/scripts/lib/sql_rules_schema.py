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
#: Words that begin a new statement. T-SQL needs no ``;``, so a depth-0 one of
#: these ends the statement being scanned.
_STATEMENT_START = frozenset(
    [
        "GO",
        "INSERT",
        "UPDATE",
        "DELETE",
        "EXEC",
        "EXECUTE",
        "MERGE",
        "CREATE",
        "ALTER",
        "DROP",
        "BEGIN",
        "DECLARE",
        "SET",
        "TRUNCATE",
    ]
)
#: Words that join one query to the next, so a ``SELECT`` after one continues it.
_SET_OPERATOR = frozenset(["UNION", "INTERSECT", "EXCEPT", "MINUS", "ALL", "DISTINCT"])
#: A word before ``(`` that opens a query, as opposed to a function call.
_QUERY_INTRO = frozenset(
    [
        "UNION", "INTERSECT", "EXCEPT", "MINUS", "ALL", "DISTINCT", "IN", "EXISTS",
        "ANY", "SOME", "AS", "FROM", "JOIN", "APPLY", "LATERAL", "ON", "WHERE",
        "AND", "OR", "NOT", "THEN", "ELSE", "WHEN", "MATERIALIZED", "INTO",
    ]
)  # fmt: skip
#: Words that cannot be the target table of an INSERT (trigger headers, ``ON``).
_NOT_A_TARGET = frozenset(["AS", "ON", "OR"])
#: Words that join two query branches. ``ALL`` and ``DISTINCT`` may follow one.
_SET_JOIN = frozenset(["UNION", "INTERSECT", "EXCEPT", "MINUS"])
#: Punctuation that a name or placeholder joins with no space, as in ``dbo.{5}_ws``.
_GLUE_PUNCT = frozenset(["{", "}", "."])


def _is(token, word: str) -> bool:
    return token.kind == WORD and token.text.upper() == word


def _adjacent(a, b) -> bool:
    """True when ``b`` starts right where ``a`` ends, with no whitespace."""
    return a.line == b.line and a.col + len(a.text) == b.col


def _render(tokens) -> str:
    """Matched tokens as one line of text, with dotted and templated names rejoined."""
    parts: list[str] = []
    for k, token in enumerate(tokens):
        is_glued = (
            k > 0
            and _adjacent(tokens[k - 1], token)
            and (tokens[k - 1].text in _GLUE_PUNCT or token.text in _GLUE_PUNCT)
        )
        if k > 0 and not is_glued:
            parts.append(" ")
        parts.append(token.text)
    return "".join(parts).replace(" . ", ".")


def _placeholder_end(tokens, i: int) -> int:
    """Index after a numbered ``{n}`` placeholder at ``i``, or ``i``."""
    if i + 2 < len(tokens) and _punct(tokens[i], "{"):
        number, close = tokens[i + 1], tokens[i + 2]
        if (
            number.kind == NUMBER
            and number.text.isdigit()
            and _punct(close, "}")
            and _adjacent(tokens[i], number)
            and _adjacent(number, close)
        ):
            return i + 3
    return i


def _piece_end(tokens, i: int) -> int:
    """Index after one word, quoted identifier, or placeholder at ``i``, or ``i``."""
    if i < len(tokens) and tokens[i].kind in (WORD, QUOTED):
        return i + 1
    return _placeholder_end(tokens, i)


def _part_end(tokens, i: int) -> int:
    """Index after one name part: pieces written with no whitespace between them.

    ``FDTEMP_{0}`` and ``{5}_WORKINGSET_{0}`` are one part each; in ``t {0}``
    the placeholder is not part of the name.
    """
    end = _piece_end(tokens, i)
    while end > i and end < len(tokens) and _adjacent(tokens[end - 1], tokens[end]):
        next_end = _piece_end(tokens, end)
        if next_end == end:
            break
        end = next_end
    return end


def _name_end(tokens, i: int) -> int:
    """Index after a possibly dotted table name starting at ``i``, or ``i``."""
    n = len(tokens)
    end = _part_end(tokens, i)
    if end == i:
        return i
    i = end
    while i + 1 < n and _punct(tokens[i], "."):
        j = i + 1
        while j < n and _punct(tokens[j], "."):
            j += 1  # T-SQL omitted schema part, as in db..t
        end = _part_end(tokens, j)
        if end == j:
            break
        i = end
    return i


def _target_end(tokens, i: int) -> int | None:
    """Index after ``INSERT [INTO] <table> [AS alias] [WITH (hints)]`` at ``i``.

    ``None`` when no target table follows.
    """
    n = len(tokens)
    j = i + 1
    if j < n and _is(tokens[j], "INTO"):
        j += 1
    end = _name_end(tokens, j)
    if end == j or tokens[j].text.upper() in _NOT_A_TARGET:
        return None  # ``AFTER INSERT, UPDATE AS`` in a trigger header, not an INSERT
    j = end
    if j + 1 < n and _is(tokens[j], "AS") and tokens[j + 1].kind in (WORD, QUOTED):
        j += 2
    if j + 1 < n and _is(tokens[j], "WITH") and _punct(tokens[j + 1], "("):
        j = _skip_group(tokens, j + 1)  # T-SQL table hint, as in WITH (TABLOCK)
    return j


def _is_column_list(tokens, j: int) -> bool:
    """True when the ``(`` at ``j`` opens a target column list, not a query."""
    n = len(tokens)
    return (
        j < n
        and _punct(tokens[j], "(")
        and not (
            j + 1 < n and (_is(tokens[j + 1], "SELECT") or _punct(tokens[j + 1], "("))
        )
    )


def _output_end(tokens, j: int) -> int | None:
    """Index after a T-SQL ``OUTPUT ...`` clause at ``j``, or ``j`` if none.

    ``None`` when the statement ends inside the clause.
    """
    n = len(tokens)
    if not (j < n and _is(tokens[j], "OUTPUT")):
        return j
    while j < n and not any(
        _is(tokens[j], w)
        for w in ("SELECT", "VALUES", "VALUE", "EXEC", "DEFAULT", "WITH")
    ):
        if _punct(tokens[j], ";"):
            return None
        j += 1
    return j


def check_positional_insert(ctx: Context) -> Iterator[Hit]:
    """An INSERT with no column list, fed by ``VALUES`` or a named ``SELECT``.

    An INSERT whose SELECT source has a star item is left to
    ``sql.schema.insert-select-star``, so the statement gets one finding.
    """
    tokens = ctx.tokens
    n = len(tokens)
    sources = _insert_sources(tokens)
    for i, token in enumerate(tokens):
        if not _is(token, "INSERT"):
            continue
        j = _target_end(tokens, i)
        if j is None or _is_column_list(tokens, j):
            continue
        body = _output_end(tokens, j)
        if (
            body is not None
            and body < n
            and (_is(tokens[body], "VALUES") or _is(tokens[body], "VALUE"))
        ):
            yield Hit(token.line, _render([*tokens[i:j], tokens[body]]))
        elif i in sources and _source_star(tokens, sources[i]) is None:
            yield Hit(token.line, _render([*tokens[i:j], tokens[sources[i][0]]]))


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


def _continues_query(tokens, k: int) -> bool:
    """True when the ``SELECT`` at ``k`` follows ``UNION`` and the like, or ``(``."""
    if k == 0:
        return False
    prev = tokens[k - 1]
    return _punct(prev, "(") or (
        prev.kind == WORD and prev.text.upper() in _SET_OPERATOR
    )


def _starts_cte(tokens, k: int) -> bool:
    """``WITH name AS`` or ``WITH RECURSIVE``, not a ``WITH (NOLOCK)`` hint."""
    nxt = tokens[k + 1] if k + 1 < len(tokens) else None
    after = tokens[k + 2] if k + 2 < len(tokens) else None
    return bool(
        nxt is not None
        and nxt.kind in (WORD, QUOTED)
        and ((after is not None and _is(after, "AS")) or _is(nxt, "RECURSIVE"))
    )


def _walk(tokens, start: int, depth: int = 0) -> Iterator[tuple[int, int]]:
    """Yield ``(index, depth)`` for the tokens of one statement from ``start``.

    ``depth`` is the paren level the token sits on: a ``(`` is yielded at the
    level it opens from, a ``)`` at the level it closes to. The walk stops at
    ``;``, at a closing paren with no opener, and at a level-0 token that begins
    another statement: a ``_STATEMENT_START`` word, a ``SELECT`` that does not
    continue the query, ``WITH name AS``, or an ``END`` with no ``CASE``.
    """
    case = 0
    for k in range(start, len(tokens)):
        token = tokens[k]
        if _punct(token, ";"):
            return
        if _punct(token, "("):
            yield k, depth
            depth += 1
            continue
        if _punct(token, ")"):
            depth -= 1
            if depth < 0:
                return
            yield k, depth
            continue
        if token.kind == WORD:
            word = token.text.upper()
            if word == "CASE":
                case += 1
            elif word == "END":
                if case:
                    case -= 1
                elif depth == 0:
                    return
            elif depth == 0 and case == 0:
                if word in _STATEMENT_START:
                    return
                if word == "SELECT" and not _continues_query(tokens, k):
                    return
                if word == "WITH" and _starts_cte(tokens, k):
                    return
        yield k, depth


def _split_items(tokens, start: int, ends: frozenset) -> list[list]:
    """Comma-separated items from ``start`` to the end of the list.

    The list ends at a level-0 word in ``ends`` or at the end of the statement.
    """
    items: list[list] = [[]]
    for k, depth in _walk(tokens, start):
        token = tokens[k]
        if depth == 0:
            if token.kind == WORD and token.text.upper() in ends:
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


def _cte_end(tokens, j: int) -> int:
    """Index after the ``WITH name AS (...)[, ...]`` definitions that start at ``j``."""
    n = len(tokens)
    j += 1
    if j < n and _is(tokens[j], "RECURSIVE"):
        j += 1
    while j < n:
        while j < n and not _is(tokens[j], "AS"):
            if _punct(tokens[j], ";"):
                return n
            j = _skip_group(tokens, j) if _punct(tokens[j], "(") else j + 1
        j += 1
        while j < n and (_is(tokens[j], "NOT") or _is(tokens[j], "MATERIALIZED")):
            j += 1
        if j >= n or not _punct(tokens[j], "("):
            return n
        j = _skip_group(tokens, j)
        if j < n and _punct(tokens[j], ","):
            j += 1
            continue
        return j
    return j


def _insert_source_start(tokens, i: int) -> int | None:
    """Index where the query the INSERT at ``i`` reads begins: ``SELECT`` or ``(``."""
    n = len(tokens)
    j = _target_end(tokens, i)
    if j is None:
        return None
    if _is_column_list(tokens, j):
        j = _skip_group(tokens, j)
    j = _output_end(tokens, j)
    if j is None:
        return None
    if j < n and _is(tokens[j], "WITH"):
        j = _cte_end(tokens, j)
    lead = j
    while lead < n and _punct(tokens[lead], "("):
        lead += 1
    if lead < n and _is(tokens[lead], "SELECT"):
        return j
    return None


def _select_end(tokens, s: int) -> int:
    """Index after the SELECT at ``s``: its statement end, closing paren, or ``UNION``."""
    end = s + 1
    for k, depth in _walk(tokens, s + 1):
        token = tokens[k]
        if depth == 0 and token.kind == WORD and token.text.upper() in _SET_JOIN:
            return k
        end = k + 1
    return end


def _query_branches(tokens, j: int, branches: list[int]) -> int:
    """Collect the SELECT branches of the query expression at ``j``.

    A branch is ``SELECT ...`` or a parenthesized query expression. Branches are
    joined by ``UNION``, ``INTERSECT``, ``EXCEPT``, or ``MINUS``, each with an
    optional ``ALL`` or ``DISTINCT``. Returns the index after the expression.
    """
    n = len(tokens)
    while j < n:
        if _is(tokens[j], "SELECT"):
            branches.append(j)
            j = _select_end(tokens, j)
        elif (
            _punct(tokens[j], "(")
            and j + 1 < n
            and (_is(tokens[j + 1], "SELECT") or _punct(tokens[j + 1], "("))
        ):
            j = _query_branches(tokens, j + 1, branches)
            if not (j < n and _punct(tokens[j], ")")):
                return j
            j += 1
        else:
            return j
        if not (
            j < n and tokens[j].kind == WORD and tokens[j].text.upper() in _SET_JOIN
        ):
            return j
        j += 1
        if j < n and (_is(tokens[j], "ALL") or _is(tokens[j], "DISTINCT")):
            j += 1
    return j


def _insert_sources(tokens) -> dict[int, list[int]]:
    """Map each ``INSERT`` index to the SELECTs that supply its rows.

    The sources are the SELECT branches of the query after the target, column
    list, and CTE definitions: plain, parenthesized, or joined by ``UNION`` and
    the like. A subquery in a ``FROM`` or ``WHERE`` clause does not count, and
    neither does anything after the statement ends.
    """
    found: dict[int, list[int]] = {}
    for i, token in enumerate(tokens):
        if not _is(token, "INSERT"):
            continue
        start = _insert_source_start(tokens, i)
        if start is None:
            continue
        branches: list[int] = []
        _query_branches(tokens, start, branches)
        if branches:
            found[i] = branches
    return found


def _source_star(tokens, sources: list[int]):
    """The first ``*`` or ``t.*`` item across an INSERT's sources, or ``None``.

    The one test that decides whether a statement is ``insert-select-star``
    or ``positional-insert``.
    """
    return next(
        (star for s in sources if (star := _star_item(tokens, s)) is not None), None
    )


def check_insert_select_star(ctx: Context) -> Iterator[Hit]:
    """``INSERT ... SELECT *`` copies whatever columns the source has."""
    tokens = ctx.tokens
    for i, sources in _insert_sources(tokens).items():
        star = _source_star(tokens, sources)
        if star is not None:
            yield Hit(tokens[i].line, _render([*tokens[i : sources[0] + 1], *star]))


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


def _group_is_query(tokens, opener: int) -> bool:
    """True when the group that opens at ``opener`` holds a query.

    The group starts with ``SELECT`` or ``WITH``, or with more parens around one.
    A nested paren right after a function name is an argument, so
    ``STRING_AGG((SELECT 1), ',' ORDER BY 1)`` is not a query.
    """
    if opener + 1 >= len(tokens):
        return False
    nxt = tokens[opener + 1]
    if _is(nxt, "SELECT") or _is(nxt, "WITH"):
        return True
    if not _punct(nxt, "("):
        return False
    before = tokens[opener - 1] if opener > 0 else None
    if (
        before is not None
        and before.kind == WORD
        and before.text.upper() not in _QUERY_INTRO
    ):
        return False
    return _group_is_query(tokens, opener + 1)


def _in_query_scope(tokens, k: int) -> bool:
    """True at statement level or inside a parenthesized query.

    ``OVER (ORDER BY a)``, ``WITHIN GROUP (ORDER BY a)``, and aggregate
    ``ORDER BY`` sort a function's input, not the result set.
    """
    opener = _enclosing_open(tokens, k)
    return opener is None or _group_is_query(tokens, opener)


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
        fix="Name the target columns: INSERT INTO t (col1, col2) VALUES (...), or INSERT INTO t (col1, col2) SELECT a, b FROM s.",
        positive=(
            Fixture("single-row", "INSERT INTO orders VALUES (1, 'a');", (1,)),
            Fixture("multi-row-lowercase", "insert into t values (1), (2);", (1,)),
            Fixture("second-statement", "SELECT 1;\nINSERT INTO s.t VALUES (1);", (2,)),
            Fixture(
                "named-select", "INSERT INTO archive SELECT id, name FROM orders;", (1,)
            ),
            Fixture(
                "union-select",
                "INSERT INTO a\nSELECT x FROM b UNION ALL SELECT y FROM c;",
                (1,),
            ),
            Fixture("parenthesized-select", "INSERT INTO a (SELECT x FROM b);", (1,)),
            Fixture(
                "cte-select",
                "INSERT INTO a WITH c AS (SELECT x FROM b) SELECT x FROM c;",
                (1,),
            ),
            Fixture("placeholder-target", "INSERT INTO t_{0} VALUES (1);", (1,)),
            Fixture(
                "placeholder-after-dot",
                "INSERT INTO dbo.{5}_ws_{0} SELECT id FROM t;",
                (1,),
            ),
        ),
        negative=(
            Fixture("column-list", "INSERT INTO orders (id, name) VALUES (1, 'a');"),
            Fixture("column-list-no-space", "insert into orders(id) values (1);"),
            Fixture("default-values", "INSERT INTO orders DEFAULT VALUES;"),
            Fixture("select-with-column-list", "INSERT INTO a (x) SELECT x FROM b;"),
            Fixture("select-star", "INSERT INTO archive SELECT * FROM orders;"),
            Fixture("placeholder-after-space", "INSERT INTO t {0} VALUES (1);"),
            Fixture(
                "placeholder-after-space-select", "INSERT INTO t {0} SELECT x FROM b;"
            ),
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
                "placeholder-target", "INSERT INTO {5}_ws_{0} SELECT * FROM b;", (1,)
            ),
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
