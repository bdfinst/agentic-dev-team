"""Correctness-trap rules: statements that run but do not do what they read as.

Four rules are script-owned. ``distinct-masks-join`` needs judgment about row
multiplicity and is agent-owned: it has no ``check``.

Stdlib-only. Python 3.10+.
"""

from __future__ import annotations

from collections.abc import Iterator

from sql_clauses import (
    NOT_A_STATEMENT_AFTER,
    SET_OPERATORS,
    is_punct,
    is_statement_start,
    matching_parens,
    render,
    segments,
    word,
)
from sql_rules import OWNER_AGENT, OWNER_SCRIPT, Context, Fixture, Hit, Rule
from sql_tokenize import PUNCT, QUOTED, WORD

NULL_EQUALITY = "sql.correctness.null-equality"
UNBOUNDED_WRITE = "sql.correctness.unbounded-write"
IMPLICIT_CROSS_JOIN = "sql.correctness.implicit-cross-join"
NOT_IN_SUBQUERY = "sql.correctness.not-in-subquery"
DISTINCT_MASKS_JOIN = "sql.correctness.distinct-masks-join"

# --- null-equality ---------------------------------------------------------

_SET_END = frozenset({"WHERE", "FROM", "RETURNING", "OUTPUT", "ON", "WHEN"})
_CALL_STARTS = frozenset({"EXEC", "EXECUTE", "CALL"})
_COMPOUND_ASSIGN = frozenset("+-*/%&|^")


def _adjacent(tokens, a: int, b: int) -> bool:
    first, second = tokens[a], tokens[b]
    return first.line == second.line and first.col + len(first.text) == second.col


def _comparison_start(tokens, i: int) -> int | None:
    """Index of the comparison operator that ends just before ``NULL`` at ``i``.

    ``=``, ``==``, ``<>``, ``!=``, ``<=``, and ``>=`` count. Assignment
    (``:=``, ``+=``), the null-safe ``<=>``, and the named argument ``=>`` do not.
    """
    p = i - 1
    if p < 0 or tokens[p].kind != PUNCT:
        return None
    q = p - 1
    before = (
        tokens[q].text
        if q >= 0 and tokens[q].kind == PUNCT and _adjacent(tokens, q, p)
        else ""
    )
    if tokens[p].text == "=":
        if before == ":" or before in _COMPOUND_ASSIGN:
            return None
        return q if before in ("<", ">", "!", "=") else p
    if tokens[p].text == ">" and before == "<":
        return q
    return None


def _is_variable_default(tokens, pairs_by_close, op: int) -> bool:
    """``@p type [(n)] = NULL``: a parameter or ``DECLARE`` default, not a test."""
    j = op - 1
    if j >= 0 and is_punct(tokens[j], ")") and j in pairs_by_close:
        j = pairs_by_close[j] - 1
    return j >= 1 and tokens[j].kind == WORD and tokens[j - 1].text.startswith("@")


def _set_clause_indexes(tokens, items: list[int]) -> set[int]:
    """Indexes inside ``SET a = ..., b = ...``, where ``=`` assigns."""
    inside: set[int] = set()
    active = False
    cases = 0  # CASE ... WHEN ... END inside a value is not the MERGE WHEN
    previous = ""
    for index in items:
        name = word(tokens[index])
        after_key = previous == "KEY"  # MySQL: ON DUPLICATE KEY UPDATE a = ...
        previous = name
        if name == "SET" or (name == "UPDATE" and after_key):
            active = True
            cases = 0
        elif active and name == "CASE":
            cases += 1
            inside.add(index)
        elif active and name == "END" and cases:
            cases -= 1
            inside.add(index)
        elif active and name in _SET_END and not (name == "WHEN" and cases):
            active = False
        elif active:
            inside.add(index)
    return inside


def _statements(tokens, items: list[int]) -> list[list[int]]:
    """Split a segment at statement starts: T-SQL needs no ``;``."""
    parts: list[list[int]] = [[]]
    for position, index in enumerate(items):
        if position and is_statement_start(tokens, items, position):
            parts.append([])
        parts[-1].append(index)
    return parts


def _in_routine_parameters(tokens, i: int) -> bool:
    """True inside the ``(...)`` of ``CREATE [OR REPLACE] FUNCTION|PROCEDURE name (...)``."""
    depth = 0
    for j in range(i - 1, -1, -1):
        if is_punct(tokens[j], ")"):
            depth += 1
        elif is_punct(tokens[j], "("):
            if depth == 0:
                names = [word(t) for t in tokens[max(j - 6, 0) : j]]
                return any(n in ("FUNCTION", "PROCEDURE", "PROC") for n in names)
            depth -= 1
        elif is_punct(tokens[j], ";"):
            return False
    return False


def check_null_equality(ctx: Context) -> Iterator[Hit]:
    """``= NULL`` and ``<> NULL`` are never true. ``IS [NOT] NULL`` is the test."""
    tokens = ctx.tokens
    pairs = matching_parens(tokens)
    by_close = {close: open_ for open_, close in pairs.items()}
    for segment in segments(tokens):
        for items in _statements(tokens, segment):
            if word(tokens[items[0]]) in _CALL_STARTS:
                continue
            assigning = _set_clause_indexes(tokens, items)
            selecting = word(tokens[items[0]]) == "SELECT"
            for i in items:
                if word(tokens[i]) != "NULL" or i in assigning:
                    continue
                op = _comparison_start(tokens, i)
                if op is None:
                    continue
                if _is_variable_default(tokens, by_close, op):
                    continue
                if _in_routine_parameters(tokens, i):
                    continue
                lhs = op - 1
                if (
                    selecting
                    and lhs >= 1
                    and tokens[lhs].text.startswith("@")
                    and (
                        word(tokens[lhs - 1]) == "SELECT"
                        or is_punct(tokens[lhs - 1], ",")
                    )
                ):
                    continue  # T-SQL: SELECT @a = 1, @b = NULL assigns
                yield Hit(tokens[i].line, render(tokens[max(lhs, 0) : i + 1]))


# --- unbounded-write -------------------------------------------------------


def _is_write_start(tokens, items: list[int], position: int) -> bool:
    """``DELETE FROM ...`` or ``UPDATE name SET ...`` as a statement."""
    token = tokens[items[position]]
    verb = word(token)
    if verb not in ("DELETE", "UPDATE"):
        return False
    if position > 0:
        previous = tokens[items[position - 1]]
        if previous.kind == PUNCT and previous.text == ",":
            return False
        if word(previous) in NOT_A_STATEMENT_AFTER:
            return False
    rest = items[position + 1 :]
    if not rest:
        return False
    first = tokens[rest[0]]
    if verb == "DELETE":
        if word(first) in ("FROM", "TOP"):
            return True
        if first.kind not in (WORD, QUOTED):
            return False
        # T-SQL allows DELETE name [WHERE ...]; FROM is optional.
        k = 1
        while (
            k + 1 < len(rest)
            and tokens[rest[k]].text == "."
            and tokens[rest[k + 1]].kind in (WORD, QUOTED)
        ):
            k += 2
        if k >= len(rest):
            return True
        return word(tokens[rest[k]]) in (
            "FROM",
            "WHERE",
            "OUTPUT",
            "OPTION",
        ) or is_statement_start(tokens, items, position + 1 + k)
    if first.kind not in (WORD, QUOTED) or word(first) == "SET":
        return False
    return any(word(tokens[i]) == "SET" for i in rest)


def check_unbounded_write(ctx: Context) -> Iterator[Hit]:
    """``UPDATE`` or ``DELETE`` with no ``WHERE``, ``LIMIT``, or ``TOP``.

    Only keywords at the statement's own depth count, so a ``WHERE`` inside a
    subquery does not bound the outer write.
    """
    tokens = ctx.tokens
    for items in segments(tokens):
        starts = [p for p in range(len(items)) if _is_write_start(tokens, items, p)]
        for position in starts:
            end = len(items)
            for later in range(position + 1, len(items)):
                if later in starts or is_statement_start(tokens, items, later):
                    end = later
                    break
            extent = items[position:end]
            names = {word(tokens[i]) for i in extent}
            if names & {"WHERE", "LIMIT", "TOP"}:
                continue
            head = []
            for i in extent[:5]:
                if word(tokens[i]) in ("SET", "WHERE"):
                    break
                head.append(tokens[i])
            yield Hit(tokens[items[position]].line, render(head))


# --- implicit-cross-join ---------------------------------------------------

_FROM_END = (
    frozenset(
        {
            "WHERE",
            "GROUP",
            "HAVING",
            "ORDER",
            "LIMIT",
            "OFFSET",
            "FETCH",
            "WINDOW",
            "RETURNING",
            "FOR",
            "OPTION",
            "QUALIFY",
            # upsert tails: ON CONFLICT ... DO UPDATE SET a = 1, b = 2
            "CONFLICT",
            "DUPLICATE",
            "DO",
            "SET",
            "UPDATE",
        }
    )
    | SET_OPERATORS
)
_NO_STATEMENT = frozenset({"GRANT", "REVOKE", "DENY"})
_TABLE_HINTS = frozenset(
    {
        "NOLOCK",
        "READUNCOMMITTED",
        "READCOMMITTED",
        "REPEATABLEREAD",
        "SERIALIZABLE",
        "HOLDLOCK",
        "ROWLOCK",
        "PAGLOCK",
        "TABLOCK",
        "TABLOCKX",
        "UPDLOCK",
        "XLOCK",
        "READPAST",
        "NOWAIT",
        "FORCESEEK",
        "NOEXPAND",
    }
)


def _is_table_source_fn(tokens, items: list[int], position: int) -> bool:
    """After a comma: ``LATERAL ...`` or ``name(...)`` is a correlated source."""
    if position >= len(items):
        return False
    first = tokens[items[position]]
    if word(first) == "LATERAL":
        return True
    j = position
    # Allow a dotted name: schema.fn(...)
    while (
        j + 2 < len(items)
        and tokens[items[j + 1]].text == "."
        and tokens[items[j]].kind in (WORD, QUOTED)
    ):
        j += 2
    if not (
        tokens[items[j]].kind in (WORD, QUOTED)
        and j + 1 < len(items)
        and is_punct(tokens[items[j + 1]], "(")
    ):
        return False
    # ``b (NOLOCK)`` is a legacy table hint, not a table function.
    after_paren = items[j + 1] + 1
    hint = tokens[after_paren] if after_paren < len(tokens) else None
    return hint is None or word(hint) not in _TABLE_HINTS


def check_implicit_cross_join(ctx: Context) -> Iterator[Hit]:
    """``FROM a, b`` with no ``WHERE`` joins every row of ``a`` to every row of ``b``."""
    tokens = ctx.tokens
    for items in segments(tokens):
        if word(tokens[items[0]]) in _NO_STATEMENT:
            continue
        names = [word(tokens[i]) for i in items]
        for start, name in enumerate(names):
            if name != "FROM":
                continue
            if start and names[start - 1] in ("DISTINCT", "DELETE"):
                continue  # IS [NOT] DISTINCT FROM, DELETE FROM
            if "SELECT" not in names[:start]:
                continue  # REVOKE ... FROM, EXTRACT(x FROM y)
            end = len(items)
            for position in range(start + 1, len(items)):
                if names[position] in _FROM_END or is_statement_start(
                    tokens, items, position
                ):
                    end = position
                    break
            if end < len(items) and names[end] == "WHERE":
                continue  # the WHERE carries the join condition
            for position in range(start + 1, end):
                token = tokens[items[position]]
                if is_punct(token, ",") and not _is_table_source_fn(
                    tokens, items, position + 1
                ):
                    shown = tokens[items[start] : items[position] + 1]
                    tail = [tokens[i] for i in items[position + 1 : position + 2]]
                    yield Hit(token.line, render([*shown, *tail]))
                    break


# --- not-in-subquery -------------------------------------------------------


def _top_level(pairs: dict[int, int], start: int, stop: int) -> list[int]:
    """Token indexes in ``[start, stop)`` outside nested groups."""
    found: list[int] = []
    i = start
    while i < stop:
        found.append(i)
        if i in pairs and pairs[i] < stop:
            found.append(pairs[i])
            i = pairs[i]
        i += 1
    return found


def _subquery_excludes_nulls(tokens, pairs: dict[int, int], open_index: int) -> bool:
    """``(SELECT c FROM ... WHERE ... c IS NOT NULL ...)``: the column cannot be NULL.

    Conservative: one selected column, no ``OR`` and no set operator anywhere in
    the subquery, and the same name in an ``IS NOT NULL`` after its ``WHERE``.
    """
    close = pairs.get(open_index)
    if close is None:
        return False
    top = _top_level(pairs, open_index + 1, close)
    names = [word(tokens[i]) for i in top]
    if names[:1] != ["SELECT"] or "FROM" not in names or "WHERE" not in names:
        return False
    if any(word(tokens[i]) == "OR" for i in range(open_index, close)):
        return False
    if any(n in SET_OPERATORS for n in names):
        return False
    selected = top[1 : names.index("FROM")]
    if selected and word(tokens[selected[0]]) in ("DISTINCT", "ALL"):
        selected = selected[1:]
    if not selected or any(is_punct(tokens[i], ",") for i in selected):
        return False
    for position, index in enumerate(selected):  # a plain, maybe dotted, name
        expected_name = position % 2 == 0
        if expected_name != (tokens[index].kind in (WORD, QUOTED)):
            return False
        if not expected_name and not is_punct(tokens[index], "."):
            return False
    column = tokens[selected[-1]].text.lower()
    for j in range(top[names.index("WHERE")], close - 3):
        if (
            tokens[j].text.lower() == column
            and word(tokens[j + 1]) == "IS"
            and word(tokens[j + 2]) == "NOT"
            and word(tokens[j + 3]) == "NULL"
        ):
            return True
    return False


def check_not_in_subquery(ctx: Context) -> Iterator[Hit]:
    """``x NOT IN (SELECT ...)`` returns no rows when the subquery yields a NULL."""
    tokens = ctx.tokens
    pairs = matching_parens(tokens)
    for i in range(len(tokens) - 3):
        if (
            word(tokens[i]) == "NOT"
            and word(tokens[i + 1]) == "IN"
            and is_punct(tokens[i + 2], "(")
            and word(tokens[i + 3]) in ("SELECT", "WITH")
        ):
            if _subquery_excludes_nulls(tokens, pairs, i + 2):
                continue
            start = max(i - 1, 0)
            yield Hit(tokens[i].line, render(tokens[start : i + 6]))


RULES = (
    Rule(
        id=NULL_EQUALITY,
        family="correctness",
        dialect="ansi",
        owner=OWNER_SCRIPT,
        severity="error",
        message="Comparing to NULL with = or <> is never true, so the predicate matches no rows.",
        fix="Use IS NULL or IS NOT NULL.",
        positive=(
            Fixture("equals", "SELECT id FROM t WHERE deleted_at = NULL", (1,)),
            Fixture("not-equals", "SELECT id FROM t WHERE deleted_at <> NULL", (1,)),
            Fixture("bang-equals", "SELECT id FROM t WHERE a != NULL", (1,)),
            Fixture(
                "second-line",
                "SELECT id\nFROM t\nWHERE a = 1\n  AND b = NULL",
                (4,),
            ),
            Fixture("in-case", "SELECT CASE WHEN a = NULL THEN 1 END FROM t", (1,)),
            Fixture(
                "where-after-set",
                "UPDATE t SET a = NULL WHERE b = NULL",
                (1,),
            ),
        ),
        negative=(
            Fixture("is-null", "SELECT id FROM t WHERE deleted_at IS NULL"),
            Fixture("is-not-null", "SELECT id FROM t WHERE deleted_at IS NOT NULL"),
            Fixture("update-set-null", "UPDATE t SET a = NULL, b = 2 WHERE id = 1"),
            Fixture("insert-values-null", "INSERT INTO t (a) VALUES (NULL)"),
            Fixture("column-default-null", "CREATE TABLE t (a int DEFAULT NULL)"),
            Fixture("tsql-param-default", "CREATE PROC p @a int = NULL AS SELECT 1"),
            Fixture("tsql-declare-default", "DECLARE @a varchar(10) = NULL"),
            Fixture("null-safe-equals", "SELECT 1 FROM t WHERE a <=> NULL"),
            Fixture("string-literal", "SELECT 1 FROM t WHERE a = 'x = NULL'"),
            Fixture("in-comment", "-- WHERE a = NULL"),
        ),
        check=check_null_equality,
    ),
    Rule(
        id=UNBOUNDED_WRITE,
        family="correctness",
        dialect="ansi",
        owner=OWNER_SCRIPT,
        severity="error",
        message="UPDATE or DELETE without a WHERE clause changes every row in the table.",
        fix="Add a WHERE clause. For an intended full-table change, use TRUNCATE or suppress this rule with a reason.",
        positive=(
            Fixture("delete-all", "DELETE FROM sessions", (1,)),
            Fixture("update-all", "UPDATE users SET active = 0", (1,)),
            Fixture(
                "where-only-in-subquery",
                "UPDATE t SET x = (SELECT y FROM u WHERE u.id = 1)",
                (1,),
            ),
            Fixture(
                "second-of-two",
                "DELETE FROM a WHERE id = 1;\nDELETE FROM b;",
                (2,),
            ),
            Fixture("tsql-no-semicolon", "DELETE FROM a\nUPDATE b SET x = 1", (1, 2)),
        ),
        negative=(
            Fixture("delete-where", "DELETE FROM sessions\nWHERE expires_at < now()"),
            Fixture("update-where", "UPDATE users SET active = 0 WHERE id = 1"),
            Fixture(
                "upsert",
                "INSERT INTO t (a) VALUES (1) ON CONFLICT (a) DO UPDATE SET a = 2",
            ),
            Fixture(
                "merge",
                "MERGE INTO t USING s ON t.id = s.id WHEN MATCHED THEN UPDATE SET a = 1",
            ),
            Fixture("select-for-update", "SELECT id FROM t WHERE id = 1 FOR UPDATE"),
            Fixture("select-for-update-bare", "SELECT id FROM t FOR UPDATE"),
            Fixture(
                "fk-actions",
                "CREATE TABLE c (p int REFERENCES p ON DELETE CASCADE ON UPDATE CASCADE)",
            ),
            Fixture("grant", "GRANT SELECT, UPDATE, DELETE ON t TO r"),
            Fixture("tsql-delete-top", "DELETE TOP (100) FROM sessions"),
            Fixture("mysql-delete-limit", "DELETE FROM sessions LIMIT 100"),
            Fixture(
                "writable-cte",
                "WITH d AS (DELETE FROM t WHERE id = 1 RETURNING *) SELECT * FROM d",
            ),
        ),
        check=check_unbounded_write,
    ),
    Rule(
        id=IMPLICIT_CROSS_JOIN,
        family="correctness",
        dialect="ansi",
        owner=OWNER_SCRIPT,
        severity="warning",
        message="A comma-separated FROM list with no WHERE joins every row to every row (a cross join).",
        fix="Write an explicit JOIN ... ON, or CROSS JOIN when the product is intended.",
        positive=(
            Fixture("two-tables", "SELECT a.x FROM a, b", (1,)),
            Fixture("three-tables", "SELECT 1 FROM a, b, c", (1,)),
            Fixture(
                "after-join",
                "SELECT 1\nFROM a JOIN b ON a.id = b.id,\n  c",
                (2,),
            ),
            Fixture(
                "subquery", "SELECT 1 FROM t WHERE id IN (SELECT 1 FROM a, b)", (1,)
            ),
            Fixture(
                "union-branch",
                "SELECT 1 FROM a WHERE x = 1 UNION SELECT 1 FROM b, c",
                (1,),
            ),
        ),
        negative=(
            Fixture("with-where", "SELECT a.x FROM a, b WHERE a.id = b.a_id"),
            Fixture("select-list-commas", "SELECT a, b FROM t"),
            Fixture("table-function", "SELECT x FROM generate_series(1, 3) AS x"),
            Fixture("lateral", "SELECT 1 FROM a, LATERAL (SELECT 1) l"),
            Fixture("correlated-function", "SELECT 1 FROM a, unnest(a.xs) AS x"),
            Fixture("explicit-join", "SELECT 1 FROM a JOIN b ON a.id = b.id"),
            Fixture("is-distinct-from", "SELECT a IS DISTINCT FROM b FROM t"),
            Fixture("extract", "SELECT EXTRACT(year FROM d), 2 FROM t"),
            Fixture("revoke", "REVOKE SELECT ON t FROM u1, u2"),
        ),
        check=check_implicit_cross_join,
    ),
    Rule(
        id=NOT_IN_SUBQUERY,
        family="correctness",
        dialect="ansi",
        owner=OWNER_SCRIPT,
        severity="warning",
        message="NOT IN (SELECT ...) returns no rows when the subquery yields a NULL.",
        fix="Use NOT EXISTS, or filter the subquery with WHERE col IS NOT NULL.",
        positive=(
            Fixture(
                "simple", "SELECT id FROM t WHERE id NOT IN (SELECT t_id FROM u)", (1,)
            ),
            Fixture(
                "multiline",
                "SELECT id\nFROM t\nWHERE id NOT IN (\n  SELECT t_id FROM u\n)",
                (3,),
            ),
            Fixture(
                "cte-body",
                "SELECT 1 WHERE 1 NOT IN (WITH x AS (SELECT 1) SELECT * FROM x)",
                (1,),
            ),
        ),
        negative=(
            Fixture("literal-list", "SELECT id FROM t WHERE id NOT IN (1, 2, 3)"),
            Fixture("in-subquery", "SELECT id FROM t WHERE id IN (SELECT t_id FROM u)"),
            Fixture(
                "not-exists", "SELECT id FROM t WHERE NOT EXISTS (SELECT 1 FROM u)"
            ),
            Fixture("in-string", "SELECT 'x NOT IN (SELECT 1)'"),
        ),
        check=check_not_in_subquery,
    ),
    Rule(
        id=DISTINCT_MASKS_JOIN,
        family="correctness",
        dialect="ansi",
        owner=OWNER_AGENT,
        severity="warning",
        message="SELECT DISTINCT over a join hides duplicate rows from a fan-out instead of fixing the join.",
        fix="Join on the key that makes rows unique, or use EXISTS or an aggregate instead of DISTINCT.",
        positive=("sql-correctness-distinct-join.sql",),
        negative=("sql-correctness-distinct-single.sql",),
    ),
)
