"""Correctness-trap and index-defeating SQL rules (#2286).

``DETECTOR_BOUNDARIES`` is the issue's boundary table, row for row. Each row
runs the real engine (all rules, path ``db/q.sql``) and counts one rule's
findings. A literal ``\\n`` in a statement is a newline, as in the issue.
"""

import sys
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PLUGIN_DIR / "scripts" / "lib"))

import sql_rules
import sql_scan

RULES = sql_rules.discover_rules()

NULL_EQ = "sql.correctness.null-equality"
WRITE = "sql.correctness.unbounded-write"
CROSS = "sql.correctness.implicit-cross-join"
NOT_IN = "sql.correctness.not-in-subquery"
FUNC = "sql.index.function-on-column"
WILDCARD = "sql.index.leading-wildcard"

DETECTOR_BOUNDARIES = [
    (NULL_EQ, "SELECT id FROM t WHERE deleted_at = NULL", 1),
    (NULL_EQ, "SELECT id FROM t WHERE deleted_at <> NULL", 1),
    (NULL_EQ, "SELECT id FROM t WHERE deleted_at IS NULL", 0),
    (WRITE, "DELETE FROM sessions", 1),
    (WRITE, "UPDATE users SET active = 0", 1),
    (WRITE, "UPDATE t SET x = (SELECT y FROM u WHERE u.id = 1)", 1),
    (WRITE, "DELETE FROM sessions\\nWHERE expires_at < now()", 0),
    (WRITE, "INSERT INTO t (a) VALUES (1) ON CONFLICT (a) DO UPDATE SET a = 2", 0),
    (
        WRITE,
        "MERGE INTO t USING s ON t.id = s.id WHEN MATCHED THEN UPDATE SET a = 1",
        0,
    ),
    (WRITE, "SELECT id FROM t WHERE id = 1 FOR UPDATE", 0),
    (CROSS, "SELECT a.x FROM a, b", 1),
    (CROSS, "SELECT a.x FROM a, b WHERE a.id = b.a_id", 0),
    (CROSS, "SELECT a, b FROM t", 0),
    (CROSS, "SELECT x FROM generate_series(1, 3) AS x", 0),
    (NOT_IN, "SELECT id FROM t WHERE id NOT IN (SELECT t_id FROM u)", 1),
    (NOT_IN, "SELECT id FROM t WHERE id NOT IN (1, 2, 3)", 0),
    (FUNC, "SELECT id FROM users WHERE LOWER(email) = 'a@b.c'", 1),
    (FUNC, "SELECT a FROM t JOIN u ON UPPER(t.c) = u.c", 1),
    (FUNC, "SELECT id FROM users WHERE email = LOWER('A@B.C')", 0),
    (FUNC, "SELECT id FROM t WHERE id IN (1, 2)", 0),
    (FUNC, "SELECT id FROM t WHERE EXISTS (SELECT 1 FROM u)", 0),
    (FUNC, "SELECT a FROM t GROUP BY a HAVING COUNT(*) > 1", 0),
    (WILDCARD, "SELECT id FROM t WHERE name LIKE '%smith'", 1),
    (WILDCARD, "SELECT id FROM t WHERE name LIKE 'smith%'", 0),
]


def count(rule_id: str, sql: str) -> int:
    findings = sql_scan.scan_text(sql, "db/q.sql", rules=RULES)
    return sum(1 for f in findings if f["rule"] == rule_id)


@pytest.mark.parametrize(
    ("rule_id", "stmt", "expected"),
    DETECTOR_BOUNDARIES,
    ids=[f"{r.split('.')[-1]}-{i}" for i, (r, _, _) in enumerate(DETECTOR_BOUNDARIES)],
)
def test_detector_boundary(rule_id, stmt, expected):
    assert count(rule_id, stmt.replace("\\n", "\n")) == expected


def test_boundary_table_covers_every_script_owned_rule_of_the_slice():
    covered = {rule for rule, _, _ in DETECTOR_BOUNDARIES}
    assert covered == {NULL_EQ, WRITE, CROSS, NOT_IN, FUNC, WILDCARD}


def test_slice_registers_the_expected_rule_ids_and_owners():
    owners = {r.id: r.owner for r in RULES if r.family in ("correctness", "index")}
    assert owners == {
        NULL_EQ: "script",
        WRITE: "script",
        CROSS: "script",
        NOT_IN: "script",
        "sql.correctness.distinct-masks-join": "agent",
        FUNC: "script",
        WILDCARD: "script",
        "sql.index.implicit-conversion": "agent",
    }


# --- Hard cases beyond the table ------------------------------------------

EXTRA_CASES = [
    # null-equality: assignments and defaults are not comparisons
    (NULL_EQ, "UPDATE t SET a = NULL WHERE id = 1", 0),
    (NULL_EQ, "UPDATE t SET a = NULL, b = NULL WHERE id = 1", 0),
    (NULL_EQ, "UPDATE t SET a = NULL WHERE b = NULL", 1),
    (NULL_EQ, "INSERT INTO t (a) VALUES (NULL)", 0),
    (NULL_EQ, "DECLARE @a varchar(10) = NULL", 0),
    (NULL_EQ, "SELECT 1 FROM t WHERE a != NULL", 1),
    (NULL_EQ, "SELECT 1 FROM t WHERE a <=> NULL", 0),
    (NULL_EQ, "SELECT 1 FROM t WHERE a IS NOT NULL", 0),
    (NULL_EQ, "SELECT CASE WHEN a = NULL THEN 1 END FROM t", 1),
    (NULL_EQ, "INSERT INTO t (a) VALUES (1) ON CONFLICT (a) DO UPDATE SET b = NULL", 0),
    # unbounded-write
    (WRITE, "DELETE FROM a WHERE id = 1;\nDELETE FROM b;", 1),
    (WRITE, "DELETE FROM a;\nDELETE FROM b;", 2),
    (WRITE, "UPDATE t SET a = 1 WHERE id IN (SELECT id FROM u)", 0),
    (WRITE, "DELETE FROM t WHERE id IN (SELECT id FROM u WHERE x = 1)", 0),
    (WRITE, "DELETE FROM t USING u WHERE t.id = u.id", 0),
    (WRITE, "UPDATE t SET a = u.a FROM u WHERE t.id = u.id", 0),
    (WRITE, "UPDATE t SET a = u.a FROM u", 1),
    (WRITE, "DELETE FROM t WHERE a = 1\nUPDATE u SET b = 2", 1),
    (
        WRITE,
        "CREATE TABLE c (p int REFERENCES p ON DELETE CASCADE ON UPDATE SET NULL)",
        0,
    ),
    (
        WRITE,
        "CREATE TRIGGER x AFTER INSERT OR UPDATE OR DELETE ON t FOR EACH ROW EXECUTE FUNCTION f()",
        0,
    ),
    (WRITE, "GRANT SELECT, UPDATE, DELETE ON t TO r", 0),
    (WRITE, "SELECT * FROM t FOR NO KEY UPDATE", 0),
    (WRITE, "INSERT INTO t (a) VALUES (1) ON DUPLICATE KEY UPDATE a = 2", 0),
    (WRITE, "MERGE INTO t USING s ON t.id = s.id WHEN MATCHED THEN DELETE", 0),
    (WRITE, "WITH d AS (DELETE FROM t RETURNING *) SELECT * FROM d", 1),
    (WRITE, "DELETE TOP (100) FROM sessions", 0),
    (WRITE, "DELETE FROM sessions LIMIT 100", 0),
    (WRITE, "-- DELETE FROM sessions", 0),
    (WRITE, "SELECT 'DELETE FROM sessions'", 0),
    # implicit-cross-join
    (CROSS, "SELECT 1 FROM a, b, c", 1),
    (CROSS, "SELECT 1 FROM a, LATERAL (SELECT 1) l", 0),
    (CROSS, "SELECT 1 FROM a, unnest(a.xs) AS x", 0),
    (CROSS, "SELECT 1 FROM a JOIN b ON a.id = b.id", 0),
    (CROSS, "SELECT 1 FROM a JOIN b ON a.id = b.id, c", 1),
    (CROSS, "SELECT a IS DISTINCT FROM b, c FROM t", 0),
    (CROSS, "SELECT EXTRACT(year FROM d), 2 FROM t", 0),
    (CROSS, "SELECT 1 FROM t WHERE id IN (SELECT 1 FROM a, b)", 1),
    (CROSS, "SELECT 1 FROM a WHERE x = 1 UNION SELECT 1 FROM b, c", 1),
    (CROSS, "SELECT 1 FROM a, b GROUP BY a.id", 1),
    (CROSS, "REVOKE SELECT ON t FROM u1, u2", 0),
    # not-in-subquery
    (NOT_IN, "SELECT id FROM t WHERE NOT EXISTS (SELECT 1 FROM u)", 0),
    (NOT_IN, "SELECT id FROM t WHERE id IN (SELECT t_id FROM u)", 0),
    (NOT_IN, "SELECT id FROM t WHERE id NOT IN (\n  SELECT t_id FROM u\n)", 1),
    (NOT_IN, "SELECT 'id NOT IN (SELECT 1)'", 0),
    # function-on-column
    (FUNC, "SELECT 1 FROM t WHERE CAST(code AS int) = 5", 1),
    (FUNC, "SELECT 1 FROM t WHERE a = 1 AND (COALESCE(b, 0) = 2 OR c = 3)", 1),
    (FUNC, "SELECT 1 FROM t WHERE LOWER(a) = 'x' AND UPPER(b) = 'Y'", 2),
    (FUNC, "SELECT 1 FROM t WHERE a = CAST('5' AS int)", 0),
    (FUNC, "SELECT 1 FROM t WHERE a = LOWER(@name)", 0),
    (FUNC, "SELECT 1 FROM t WHERE y = EXTRACT(year FROM NOW())", 0),
    (FUNC, "SELECT LOWER(email) FROM users WHERE id = 1", 0),
    (FUNC, "SELECT 1 FROM t WHERE id IN (SELECT LOWER(x) FROM u)", 0),
    (FUNC, "SELECT 1 FROM t WHERE id IN (SELECT 1 FROM u WHERE LOWER(x) = 'a')", 1),
    (FUNC, "CREATE INDEX i ON t (LOWER(email))", 0),
    (FUNC, "CREATE TABLE c (p int REFERENCES p ON DELETE CASCADE)", 0),
    (FUNC, "SELECT 1 FROM t WHERE CONTAINS(body, 'x')", 0),
    (FUNC, "UPDATE t SET a = LOWER(a) WHERE id = 1", 0),
    (FUNC, "SELECT 1 FROM t WHERE created_at > NOW()", 0),
    (FUNC, "SELECT 1 FROM t GROUP BY a HAVING MAX(LOWER(b)) = 'x'", 0),
    (FUNC, "SELECT 1 FROM t JOIN u ON t.a = u.a WHERE LOWER(t.b) = 'x'", 1),
    # leading-wildcard
    (WILDCARD, "SELECT id FROM t WHERE name LIKE '%smith%'", 1),
    (WILDCARD, "SELECT id FROM t WHERE name NOT LIKE '%smith'", 1),
    (WILDCARD, "SELECT id FROM t WHERE name ILIKE '%smith'", 1),
    (WILDCARD, "SELECT id FROM t WHERE name LIKE N'%smith'", 1),
    (WILDCARD, "SELECT id FROM t WHERE name LIKE CONCAT('%', @q)", 1),
    (WILDCARD, "SELECT id FROM t WHERE name LIKE 'a%b'", 0),
    (WILDCARD, "SELECT id FROM t WHERE name LIKE @pattern", 0),
    (WILDCARD, "CREATE TABLE a (LIKE b)", 0),
    (WILDCARD, "SELECT 'name LIKE ''%x'''", 0),
]


@pytest.mark.parametrize(
    ("rule_id", "stmt", "expected"),
    EXTRA_CASES,
    ids=[f"{r.split('.')[-1]}-{i}" for i, (r, _, _) in enumerate(EXTRA_CASES)],
)
def test_extra_boundary(rule_id, stmt, expected):
    assert count(rule_id, stmt) == expected


# --- Review findings on #2292: clause extents and statement boundaries ------

EXTENT_CASES = [
    # A WHERE at the end of a segment must stop at the segment, not the file.
    (FUNC, "DELETE FROM a WHERE id = 1;\nINSERT INTO audit (msg) VALUES ('x');", 0),
    (
        FUNC,
        (
            "SELECT id FROM t WHERE id IN (SELECT t_id FROM u WHERE active = 1) "
            "ORDER BY LOWER(name)"
        ),
        0,
    ),
    (
        FUNC,
        "SELECT 1 FROM t WHERE LOWER(a) = 'x';\nSELECT 1 FROM u WHERE LOWER(b) = 'y'",
        2,
    ),
    (
        FUNC,
        (
            "INSERT INTO t SELECT x FROM u WHERE y = 1 "
            "ON CONFLICT (a) DO UPDATE SET a = LOWER(excluded.a)"
        ),
        0,
    ),
    (FUNC, "SELECT 1 FROM t WHERE a = 1\nUPDATE u SET b = LOWER(c)", 0),
    (FUNC, "SELECT 1 FROM t WHERE a = 1\nSELECT LOWER(b) FROM u", 0),
    (FUNC, "SELECT 1 FROM t WHERE a = 1\nDECLARE @x int = ABS(@y)", 0),
    # CASE ... WHEN inside SET is not the MERGE WHEN that ends SET.
    (NULL_EQ, "UPDATE t SET a = CASE WHEN b = 1 THEN 2 END, c = NULL WHERE id = 1", 0),
    (NULL_EQ, "UPDATE t SET a = CASE WHEN b = 1 THEN 2 END WHERE id = NULL", 1),
    # A T-SQL table hint is not a new statement.
    (WRITE, "UPDATE t WITH (ROWLOCK) SET x = 1 WHERE id = 1", 0),
    (WRITE, "DELETE FROM t WITH (ROWLOCK) WHERE id = 1", 0),
    (WRITE, "DELETE FROM t WITH (ROWLOCK)", 1),
    (WRITE, "WITH d AS (SELECT 1) DELETE FROM t", 1),
    # The FROM list ends at an upsert tail or the next statement.
    (
        CROSS,
        "INSERT INTO t SELECT x FROM u ON CONFLICT (a) DO UPDATE SET a = 1, b = 2",
        0,
    ),
    (CROSS, "INSERT INTO t SELECT x FROM u ON DUPLICATE KEY UPDATE a = 1, b = 2", 0),
    (CROSS, "SELECT x FROM t\nUPDATE u SET a = 1, b = 2", 0),
    (CROSS, "SELECT x FROM t\nINSERT INTO u VALUES (1), (2)", 0),
    (CROSS, "SELECT @n = COUNT(*) FROM orders\nDECLARE @a int, @b int", 0),
    (CROSS, "SELECT a.x FROM a, b\nSELECT y FROM c WHERE id = 1", 1),
    (CROSS, "SELECT x FROM t WHERE id = 1\nSELECT a.x FROM a, b", 1),
    (CROSS, "SELECT a.x FROM a, b WITH (NOLOCK)", 1),
    # NOT IN is safe when the subquery filters its own column to NOT NULL.
    (
        NOT_IN,
        "SELECT id FROM t WHERE id NOT IN (SELECT t_id FROM u WHERE t_id IS NOT NULL)",
        0,
    ),
    (
        NOT_IN,
        (
            "SELECT id FROM t WHERE id NOT IN "
            "(SELECT u.t_id FROM u WHERE u.x = 1 AND u.t_id IS NOT NULL)"
        ),
        0,
    ),
    (
        NOT_IN,
        "SELECT id FROM t WHERE id NOT IN (SELECT t_id FROM u WHERE x IS NOT NULL)",
        1,
    ),
    (
        NOT_IN,
        (
            "SELECT id FROM t WHERE id NOT IN "
            "(SELECT t_id FROM u WHERE t_id IS NOT NULL OR x = 1)"
        ),
        1,
    ),
    (
        NOT_IN,
        (
            "SELECT id FROM t WHERE id NOT IN "
            "(SELECT t_id FROM u WHERE t_id IS NOT NULL UNION SELECT t_id FROM v)"
        ),
        1,
    ),
]


@pytest.mark.parametrize(
    ("rule_id", "stmt", "expected"),
    EXTENT_CASES,
    ids=[f"{r.split('.')[-1]}-{i}" for i, (r, _, _) in enumerate(EXTENT_CASES)],
)
def test_clause_extent_and_statement_boundaries(rule_id, stmt, expected):
    assert count(rule_id, stmt) == expected


# --- Engine behavior for the new rules ------------------------------------


def test_hit_lines_and_text_name_the_statement():
    sql = "SELECT 1;\nDELETE FROM sessions;\n"
    findings = [
        f
        for f in sql_scan.scan_text(sql, "db/q.sql", rules=RULES)
        if f["rule"] == WRITE
    ]
    assert [(f["line"], f["text"]) for f in findings] == [(2, "DELETE FROM sessions")]
    assert findings[0]["severity"] == "error"


@pytest.mark.parametrize("rule_id", [NULL_EQ, WRITE, CROSS, NOT_IN, FUNC, WILDCARD])
def test_suppression_marker_silences_only_the_named_rule(rule_id):
    sql = {
        NULL_EQ: "SELECT 1 FROM t WHERE a = NULL",
        WRITE: "DELETE FROM t",
        CROSS: "SELECT 1 FROM a, b",
        NOT_IN: "SELECT 1 FROM t WHERE id NOT IN (SELECT 1 FROM u)",
        FUNC: "SELECT 1 FROM t WHERE LOWER(a) = 'x'",
        WILDCARD: "SELECT 1 FROM t WHERE a LIKE '%x'",
    }[rule_id]
    assert count(rule_id, sql) == 1
    assert count(rule_id, f"-- sql-review: ignore {rule_id}\n{sql}") == 0
    other = "sql.schema.positional-insert"
    assert count(rule_id, f"-- sql-review: ignore {other}\n{sql}") == 1


def test_a_clean_statement_trips_none_of_the_new_rules():
    sql = (
        "SELECT o.id FROM orders o JOIN items i ON i.order_id = o.id\n"
        "WHERE o.deleted_at IS NULL AND i.sku LIKE 'ab%' AND o.id NOT IN (1, 2);\n"
        "UPDATE orders SET status = 'x' WHERE id = 1;\n"
    )
    ids = {f["rule"] for f in sql_scan.scan_text(sql, "db/q.sql", rules=RULES)}
    assert not {i for i in ids if i.startswith(("sql.correctness.", "sql.index."))}


def test_unbalanced_and_empty_input_do_not_raise():
    for sql in [
        "",
        "(",
        ")",
        "SELECT ( FROM",
        "DELETE",
        "UPDATE",
        "x NOT IN (",
        "LIKE",
    ]:
        sql_scan.scan_text(sql, "db/q.sql", rules=RULES)
