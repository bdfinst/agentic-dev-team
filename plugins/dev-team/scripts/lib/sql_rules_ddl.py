"""DDL rules: unsafe migrations and dialect-specific statements.

Four script-owned rules and one agent-owned rule (``type-narrowing``, which
needs the earlier column type from another statement). The matchers share one
statement splitter so a rule never reads into the next statement.

Stdlib-only. Python 3.10+.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence

from sql_dialect import is_batch_separator
from sql_rules import OWNER_AGENT, OWNER_SCRIPT, Context, Fixture, Hit, Rule
from sql_tokenize import PUNCT, WORD

NOLOCK = "sql.ddl.nolock"
INDEX_NOT_CONCURRENT = "sql.ddl.index-not-concurrent"
BREAKING_COLUMN_CHANGE = "sql.ddl.breaking-column-change"
NOT_NULL_WITHOUT_DEFAULT = "sql.ddl.not-null-without-default"
TYPE_NARROWING = "sql.ddl.type-narrowing"

#: Words that start a new statement when a script has no ``;`` between them.
_STATEMENT_STARTS = frozenset(
    {"ALTER", "CREATE", "INSERT", "SELECT", "EXEC", "EXECUTE", "UPDATE", "DELETE"}
)
#: ``ON DELETE``, ``ON UPDATE``, and ``FOR UPDATE`` continue a statement.
_CLAUSE_LEADS = frozenset({"ON", "FOR"})
#: A column definition with one of these words supplies its own value.
_SELF_FILLING = frozenset(
    {"DEFAULT", "IDENTITY", "GENERATED", "SERIAL", "BIGSERIAL", "SMALLSERIAL"}
)
#: ``ADD <word>`` where the word starts a constraint, not a column.
_NOT_A_COLUMN = frozenset(
    {"CONSTRAINT", "PRIMARY", "FOREIGN", "UNIQUE", "CHECK", "INDEX", "PERIOD"}
)


def _word(token) -> str:
    """Uppercase text of a word token, or ``""`` for any other kind."""
    return token.text.upper() if token.kind == WORD else ""


def _words(tokens: Sequence, i: int, *expected: str) -> bool:
    """True when the tokens from ``i`` are the ``expected`` words in order."""
    if i + len(expected) > len(tokens):
        return False
    return all(_word(tokens[i + k]) == w for k, w in enumerate(expected))


def _render(tokens) -> str:
    return " ".join(t.text for t in tokens)


def _statements(tokens: Sequence) -> Iterator[Sequence]:
    """Split tokens at ``;``, ``GO``, and an unseparated statement keyword."""
    current: list = []
    depth = 0
    for i, token in enumerate(tokens):
        if token.kind == PUNCT and token.text in "()":
            depth += 1 if token.text == "(" else -1
            depth = max(depth, 0)
        if depth == 0 and token.kind == PUNCT and token.text == ";":
            if current:
                yield current
            current = []
            continue
        if depth == 0 and is_batch_separator(tokens, i):
            if current:
                yield current
            current = []
            continue
        starts = _word(token) in _STATEMENT_STARTS
        led = bool(current) and _word(current[-1]) in _CLAUSE_LEADS
        if depth == 0 and starts and current and not led:
            yield current
            current = []
        current.append(token)
    if current:
        yield current


# --- sql.ddl.nolock ---------------------------------------------------------

_DIRTY_HINTS = frozenset({"NOLOCK", "READUNCOMMITTED"})


def check_nolock(ctx: Context) -> Iterator[Hit]:
    """``WITH (NOLOCK)`` and ``SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED``."""
    tokens = ctx.tokens
    for i, token in enumerate(tokens):
        if _words(
            tokens, i, "SET", "TRANSACTION", "ISOLATION", "LEVEL", "READ", "UNCOMMITTED"
        ):
            yield Hit(token.line, _render(tokens[i : i + 6]))
        elif (
            _word(token) == "WITH" and i + 1 < len(tokens) and tokens[i + 1].text == "("
        ):
            j, depth = i + 2, 1
            while j < len(tokens) and depth:
                depth += (tokens[j].text == "(") - (tokens[j].text == ")")
                if _word(tokens[j]) in _DIRTY_HINTS:
                    yield Hit(token.line, _render(tokens[i : j + 1]))
                    break
                j += 1


# --- sql.ddl.index-not-concurrent -------------------------------------------


def check_index_not_concurrent(ctx: Context) -> Iterator[Hit]:
    """``CREATE [UNIQUE] INDEX`` without ``CONCURRENTLY``."""
    tokens = ctx.tokens
    for i, token in enumerate(tokens):
        if _word(token) != "CREATE":
            continue
        j = (
            i + 2
            if _word(tokens[i + 1] if i + 1 < len(tokens) else token) == "UNIQUE"
            else i + 1
        )
        if j < len(tokens) and _word(tokens[j]) == "INDEX":
            nxt = tokens[j + 1] if j + 1 < len(tokens) else None
            if nxt is None or _word(nxt) != "CONCURRENTLY":
                yield Hit(token.line, _render(tokens[i : j + 1]))


# --- sql.ddl.breaking-column-change -----------------------------------------


def check_breaking_column_change(ctx: Context) -> Iterator[Hit]:
    """``RENAME COLUMN`` and ``DROP COLUMN``."""
    tokens = ctx.tokens
    for i, token in enumerate(tokens):
        if _words(tokens, i, "RENAME", "COLUMN") or _words(tokens, i, "DROP", "COLUMN"):
            yield Hit(token.line, _render(tokens[i : i + 2]))


# --- sql.ddl.not-null-without-default ---------------------------------------


def _add_segments(statement: Sequence) -> Iterator[Sequence]:
    """Tokens of each ``ADD [COLUMN] ...`` clause of an ``ALTER TABLE`` statement."""
    if not _words(statement, 0, "ALTER", "TABLE"):
        return
    depth = 0
    segment: list | None = None
    for token in statement:
        if token.kind == PUNCT and token.text in "()":
            depth = max(depth + (1 if token.text == "(" else -1), 0)
        if depth == 0 and token.kind == PUNCT and token.text == ",":
            if segment is not None:
                yield segment
            segment = None
            continue
        if segment is not None:
            segment.append(token)
        elif depth == 0 and _word(token) == "ADD":
            segment = [token]
    if segment is not None:
        yield segment


def _is_not_null_without_default(segment: Sequence) -> bool:
    rest = segment[1:]
    if rest and _word(rest[0]) == "COLUMN":
        rest = rest[1:]
    if not rest or _word(rest[0]) in _NOT_A_COLUMN:
        return False
    names = {_word(t) for t in rest}
    has_not_null = any(_words(rest, i, "NOT", "NULL") for i in range(len(rest)))
    return has_not_null and not names & _SELF_FILLING


def check_not_null_without_default(ctx: Context) -> Iterator[Hit]:
    """``ALTER TABLE ... ADD [COLUMN] c type NOT NULL`` with no default."""
    for statement in _statements(ctx.tokens):
        for segment in _add_segments(statement):
            if _is_not_null_without_default(segment):
                yield Hit(segment[0].line, _render(segment))


RULES = (
    Rule(
        id=NOLOCK,
        family="ddl",
        dialect="tsql",
        owner=OWNER_SCRIPT,
        severity="warning",
        message="NOLOCK and READ UNCOMMITTED can return uncommitted, duplicated, or missing rows.",
        fix="Remove the hint, or enable READ_COMMITTED_SNAPSHOT and read committed data.",
        positive=(
            Fixture("table-hint", "SELECT id FROM t WITH (NOLOCK);", (1,)),
            Fixture("hint-list", "SELECT id FROM t WITH (INDEX(ix), NOLOCK);", (1,)),
            Fixture(
                "isolation-level",
                "SELECT 1;\nSET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;",
                (2,),
            ),
        ),
        negative=(
            Fixture("plain-select", "SELECT id FROM t;"),
            Fixture("other-hint", "SELECT id FROM t WITH (ROWLOCK);"),
            Fixture("in-comment", "-- WITH (NOLOCK)"),
            Fixture("committed", "SET TRANSACTION ISOLATION LEVEL READ COMMITTED;"),
        ),
        check=check_nolock,
    ),
    Rule(
        id=INDEX_NOT_CONCURRENT,
        family="ddl",
        dialect="postgres",
        owner=OWNER_SCRIPT,
        severity="warning",
        message="CREATE INDEX without CONCURRENTLY blocks writes to the table while it builds.",
        fix="Use CREATE INDEX CONCURRENTLY, in a migration that runs outside a transaction.",
        positive=(
            Fixture("plain", "CREATE INDEX ix ON t (c);", (1,)),
            Fixture("unique", "CREATE UNIQUE INDEX ix ON t (c);", (1,)),
            Fixture("second-statement", "SELECT 1;\ncreate index ix on t (c);", (2,)),
        ),
        negative=(
            Fixture("concurrently", "CREATE INDEX CONCURRENTLY ix ON t (c);"),
            Fixture(
                "unique-concurrently", "CREATE UNIQUE INDEX CONCURRENTLY ix ON t (c);"
            ),
            Fixture("create-table", "CREATE TABLE t (c int);"),
            Fixture("in-comment", "-- CREATE INDEX ix ON t (c)"),
        ),
        check=check_index_not_concurrent,
    ),
    Rule(
        id=BREAKING_COLUMN_CHANGE,
        family="ddl",
        dialect="ansi",
        owner=OWNER_SCRIPT,
        severity="error",
        message="Renaming or dropping a column breaks any deployed code that still uses it.",
        fix="Expand and contract: add the new column, migrate readers, drop the old one in a later release.",
        positive=(
            Fixture("rename", "ALTER TABLE t RENAME COLUMN qty TO quantity;", (1,)),
            Fixture("drop", "ALTER TABLE t DROP COLUMN qty;", (1,)),
            Fixture(
                "drop-after-add",
                "ALTER TABLE t ADD COLUMN c int;\nALTER TABLE t DROP COLUMN qty;",
                (2,),
            ),
        ),
        negative=(
            Fixture("add", "ALTER TABLE t ADD COLUMN c int;"),
            Fixture("rename-table", "ALTER TABLE t RENAME TO u;"),
            Fixture("in-comment", "-- ALTER TABLE t DROP COLUMN qty"),
        ),
        check=check_breaking_column_change,
    ),
    Rule(
        id=NOT_NULL_WITHOUT_DEFAULT,
        family="ddl",
        dialect="ansi",
        owner=OWNER_SCRIPT,
        severity="error",
        message="Adding a NOT NULL column without a default fails or locks the table when it has rows.",
        fix="Add the column nullable, backfill it, then enforce NOT NULL in a later release.",
        positive=(
            Fixture("add-column", "ALTER TABLE t ADD COLUMN c int NOT NULL;", (1,)),
            Fixture("tsql-add", "ALTER TABLE t ADD c int NOT NULL\nGO", (1,)),
            Fixture(
                "second-clause",
                "ALTER TABLE t\n  ADD COLUMN a int,\n  ADD COLUMN b int NOT NULL;",
                (3,),
            ),
            Fixture(
                "default-in-next-statement",
                "ALTER TABLE t ADD c int NOT NULL\nALTER TABLE u ADD d int DEFAULT 0",
                (1,),
            ),
        ),
        negative=(
            Fixture(
                "with-default", "ALTER TABLE t ADD COLUMN c int NOT NULL DEFAULT 0;"
            ),
            Fixture("nullable", "ALTER TABLE t ADD COLUMN c int;"),
            Fixture("create-table", "CREATE TABLE t (c int NOT NULL);"),
            Fixture("constraint", "ALTER TABLE t ADD CONSTRAINT pk PRIMARY KEY (id);"),
            Fixture("set-not-null", "ALTER TABLE t ALTER COLUMN c SET NOT NULL;"),
        ),
        check=check_not_null_without_default,
    ),
    Rule(
        id=TYPE_NARROWING,
        family="ddl",
        dialect="ansi",
        owner=OWNER_AGENT,
        severity="error",
        message="Changing a column to a narrower type, such as bigint to int, fails or truncates existing values.",
        fix="Keep the wider type, or add a new column, copy the data after checking its range, and switch readers.",
        positive=("sql-ddl-type-narrowing.sql",),
        negative=("sql-ddl-type-widening.sql",),
    ),
)
