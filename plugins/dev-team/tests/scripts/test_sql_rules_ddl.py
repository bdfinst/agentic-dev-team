"""Dialect inference, unsafe DDL, and dialect-specific rules (#2287).

One test (or one parametrized table) per Gherkin scenario in the issue. Tables
write a newline as ``\\n`` in the statement column, as the issue does.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(SCRIPTS_DIR / "lib"))

import sql_dialect
import sql_scan

CLI = SCRIPTS_DIR / "sql_anti_patterns.py"
INDEX = "sql.ddl.index-not-concurrent"
NOLOCK = "sql.ddl.nolock"
POSITIONAL = "sql.schema.positional-insert"


def text_of(cell: str) -> str:
    """A table cell with ``\\n`` turned into a newline."""
    return cell.replace("\\n", "\n")


def scan_cli(root, sql, *flags):
    path = Path(root) / "db" / "m.sql"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text_of(sql), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(CLI), *flags, "db/m.sql"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)["findings"]


def rule_ids(findings):
    return [f["rule"] for f in findings]


def scan_rule(sql, rule, dialect):
    findings = sql_scan.scan_text(text_of(sql), "db/m.sql", dialect=dialect)
    return [f for f in findings if f["rule"] == rule]


# --- Scenario Outline: Dialect inference ------------------------------------


@pytest.mark.parametrize(
    ("evidence", "dialect"),
    [
        ("SELECT TOP 5 id FROM [dbo].[t]\\nGO", "tsql"),
        ("SELECT id::text FROM t RETURNING id", "postgres"),
        ("SELECT id FROM t", "ansi"),
        ("SELECT TOP 5 id FROM t; SELECT id::text", "ansi"),
    ],
)
def test_dialect_inference(evidence, dialect):
    assert sql_dialect.infer_dialect("db/m.sql", text_of(evidence)) == dialect


@pytest.mark.parametrize(
    ("evidence", "dialect"),
    [
        ("SELECT id FROM t\\nGO", "tsql"),
        ("SELECT [id] FROM t", "tsql"),
        ("SELECT TOP (5) id FROM t", "tsql"),
        ("SELECT id FROM t WITH (NOLOCK)", "tsql"),
        ("CREATE TABLE t (n NVARCHAR(10))", "tsql"),
        ("SELECT id::text FROM t", "postgres"),
        ("CREATE FUNCTION f() RETURNS int AS $$ SELECT 1 $$", "postgres"),
        ("DELETE FROM t RETURNING id", "postgres"),
        ("SELECT id FROM t WHERE n ILIKE 'a%'", "postgres"),
        ("CREATE TABLE t (id SERIAL)", "postgres"),
        ("ALTER TABLE t ADD COLUMN id SERIAL", "postgres"),
        ("CREATE INDEX CONCURRENTLY ix ON t (c)", "postgres"),
    ],
)
def test_each_marker_alone_decides_the_dialect(evidence, dialect):
    assert sql_dialect.infer_dialect("db/m.sql", text_of(evidence)) == dialect


@pytest.mark.parametrize(
    "text",
    [
        "-- WITH (NOLOCK)\\nSELECT 1",
        "SELECT 'RETURNING id'",
        "SELECT a[1] FROM t",
        "SELECT 1 /* id::text */",
        "SELECT go FROM t",
        "SELECT 1 GO 5",
        "SELECT top FROM t",
        "SELECT top, x FROM t",
        "SELECT a:b FROM t",
        "SELECT serial FROM devices",
        "ALTER TABLE devices ADD COLUMN serial varchar(32)",
        "CREATE TABLE devices (id int, serial varchar(32))",
        "GRANT SELECT ON SCHEMA::sales TO app",
        "SELECT * FROM OBJECT::dbo.t",
        "SELECT geography::Point(1, 2, 4326)",
        "SELECT type::text FROM t",
    ],
)
def test_markers_in_comments_strings_and_lookalikes_do_not_count(text):
    assert sql_dialect.infer_dialect("db/m.sql", text_of(text)) == "ansi"


def test_a_tsql_scope_qualifier_does_not_make_a_postgres_file(tmp_path):
    sql = "GRANT SELECT ON SCHEMA::sales TO app;\\nCREATE INDEX ix ON sales.t (c);"
    assert INDEX not in rule_ids(scan_cli(tmp_path, sql))


def test_a_column_named_serial_does_not_hide_a_tsql_file(tmp_path):
    findings = scan_cli(tmp_path, "SELECT serial FROM devices WITH (NOLOCK);")
    assert rule_ids(findings) == [NOLOCK]


# --- Scenario Outline: --dialect overrides inference -------------------------


@pytest.mark.parametrize(("dialect", "count"), [("postgres", 1), ("tsql", 0)])
def test_dialect_flag_overrides_inference(tmp_path, dialect, count):
    findings = scan_cli(tmp_path, "CREATE INDEX ix ON t (c)", "--dialect", dialect)
    assert rule_ids(findings).count(INDEX) == count


def test_flag_beats_contrary_evidence(tmp_path):
    sql = "SELECT TOP 5 id FROM [dbo].[t] WITH (NOLOCK)\\nGO"
    assert rule_ids(scan_cli(tmp_path, sql)) == [NOLOCK]
    assert rule_ids(scan_cli(tmp_path, sql, "--dialect", "postgres")) == []


# --- Scenario Outline: ANSI rules fire on every dialect ----------------------


@pytest.mark.parametrize(
    ("dialect", "stmt"),
    [
        ("ansi", "INSERT INTO t VALUES (1)"),
        ("tsql", "INSERT INTO [dbo].[t] VALUES (1)\\nGO"),
        ("postgres", "INSERT INTO public.t VALUES (1::int)"),
    ],
)
def test_ansi_rules_fire_on_every_dialect(tmp_path, dialect, stmt):
    inferred = scan_cli(tmp_path, stmt)
    forced = scan_cli(tmp_path, stmt, "--dialect", dialect)
    for findings in (inferred, forced):
        assert rule_ids(findings) == [POSITIONAL]
        assert findings[0]["dialect"] == "ansi"
    assert sql_dialect.infer_dialect("db/m.sql", text_of(stmt)) == dialect


# --- Scenario Outline: Dialect and DDL rule boundaries -----------------------

BOUNDARIES = [
    ("tsql", NOLOCK, "SELECT id FROM t WITH (NOLOCK)", 1),
    ("tsql", NOLOCK, "SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED", 1),
    ("tsql", NOLOCK, "SELECT id FROM t", 0),
    ("tsql", NOLOCK, "-- WITH (NOLOCK)", 0),
    ("postgres", INDEX, "CREATE INDEX ix ON t (c)", 1),
    ("postgres", INDEX, "CREATE UNIQUE INDEX ix ON t (c)", 1),
    ("postgres", INDEX, "CREATE INDEX CONCURRENTLY ix ON t (c)", 0),
    ("tsql", INDEX, "CREATE INDEX ix ON t (c)", 0),
    (
        "ansi",
        "sql.ddl.breaking-column-change",
        "ALTER TABLE t RENAME COLUMN qty TO quantity",
        1,
    ),
    ("ansi", "sql.ddl.breaking-column-change", "ALTER TABLE t DROP COLUMN qty", 1),
    ("ansi", "sql.ddl.breaking-column-change", "ALTER TABLE t ADD COLUMN c int", 0),
    (
        "ansi",
        "sql.ddl.not-null-without-default",
        "ALTER TABLE t ADD COLUMN c int NOT NULL",
        1,
    ),
    (
        "tsql",
        "sql.ddl.not-null-without-default",
        "ALTER TABLE t ADD c int NOT NULL",
        1,
    ),
    (
        "ansi",
        "sql.ddl.not-null-without-default",
        "ALTER TABLE t ADD COLUMN c int NOT NULL DEFAULT 0",
        0,
    ),
    ("ansi", "sql.ddl.not-null-without-default", "ALTER TABLE t ADD COLUMN c int", 0),
    (
        "ansi",
        "sql.ddl.not-null-without-default",
        "CREATE TABLE t (c int NOT NULL)",
        0,
    ),
]


RULE_DIALECT = {
    NOLOCK: "tsql",
    INDEX: "postgres",
    "sql.ddl.breaking-column-change": "ansi",
    "sql.ddl.not-null-without-default": "ansi",
}

#: Rows that also run through the CLI, to prove the ``--dialect`` plumbing.
CLI_ROWS = [BOUNDARIES[0], BOUNDARIES[4], BOUNDARIES[7], BOUNDARIES[8]]


@pytest.mark.parametrize(("dialect", "rule", "stmt", "count"), CLI_ROWS)
def test_boundaries_through_the_cli(tmp_path, dialect, rule, stmt, count):
    findings = scan_cli(tmp_path, stmt, "--dialect", dialect)
    assert rule_ids(findings).count(rule) == count


@pytest.mark.parametrize(("dialect", "rule", "stmt", "count"), BOUNDARIES)
def test_dialect_and_ddl_rule_boundaries(dialect, rule, stmt, count):
    hits = scan_rule(stmt, rule, dialect)
    assert len(hits) == count
    for hit in hits:
        assert hit["line"] == 1
        assert hit["dialect"] == RULE_DIALECT[rule]


# --- Scenario: Dialect-tagged rules do not cross-fire ------------------------


def test_dialect_tagged_rules_do_not_cross_fire_on_shared_syntax(tmp_path):
    sql = "CREATE INDEX ix ON t (c);\\nSELECT id FROM t WITH (NOLOCK);"
    findings = scan_cli(tmp_path, sql, "--dialect", "tsql")
    assert NOLOCK in rule_ids(findings)
    assert [f for f in findings if f["dialect"] == "postgres"] == []


def test_inferred_tsql_file_does_not_cross_fire(tmp_path):
    sql = "CREATE INDEX ix ON t (c)\\nSELECT TOP 1 id FROM [t] WITH (NOLOCK)\\nGO"
    findings = scan_cli(tmp_path, sql)
    assert rule_ids(findings) == [NOLOCK]


# --- Scenario: Inference alone enables a dialect rule ------------------------


def test_inference_alone_enables_a_dialect_rule(tmp_path):
    findings = scan_cli(
        tmp_path, "CREATE INDEX ix ON t (c); DELETE FROM t RETURNING id"
    )
    assert INDEX in rule_ids(findings)


def test_without_evidence_a_dialect_rule_stays_quiet(tmp_path):
    assert INDEX not in rule_ids(scan_cli(tmp_path, "CREATE INDEX ix ON t (c)"))


# --- Scenario: Postgres-scanned file never yields a tsql finding -------------


def test_postgres_scanned_file_never_yields_a_tsql_finding(tmp_path):
    findings = scan_cli(
        tmp_path, "SELECT id FROM t WITH (NOLOCK)", "--dialect", "postgres"
    )
    assert NOLOCK not in rule_ids(findings)
    assert [f for f in findings if f["dialect"] == "tsql"] == []


# --- Matcher details beyond the issue's rows ---------------------------------


@pytest.mark.parametrize(
    ("stmt", "lines"),
    [
        ("SELECT 1;\nSELECT id FROM t WITH (INDEX(ix), NOLOCK);", [2]),
        ("SELECT id FROM t WITH (READUNCOMMITTED)", [1]),
        ("SELECT id FROM t (NOLOCK);", [1]),
        ("SELECT id FROM t x (NOLOCK) JOIN u (NOLOCK) ON 1 = 1", [1, 1]),
        ("SELECT f(ROWLOCK)", []),
        ("SELECT id FROM t WITH (ROWLOCK)", []),
        ("SET TRANSACTION ISOLATION LEVEL READ COMMITTED", []),
    ],
)
def test_nolock_variants(stmt, lines):
    assert [h["line"] for h in scan_rule(stmt, NOLOCK, "tsql")] == lines


@pytest.mark.parametrize(
    ("stmt", "lines"),
    [
        ("ALTER TABLE t\n  ADD COLUMN a int,\n  ADD COLUMN b int NOT NULL;", [3]),
        ("ALTER TABLE t ADD CONSTRAINT pk PRIMARY KEY (id);", []),
        ("ALTER TABLE t ALTER COLUMN c SET NOT NULL;", []),
        ("ALTER TABLE t ADD c int NOT NULL IDENTITY(1,1)", []),
        ("ALTER TABLE t ADD COLUMN c int GENERATED ALWAYS AS IDENTITY NOT NULL", []),
        ("ALTER TABLE t ADD COLUMN c SERIAL NOT NULL", []),
        ("ALTER TABLE t ADD COLUMN c BIGSERIAL NOT NULL", []),
        ("ALTER TABLE t ADD COLUMN c SMALLSERIAL NOT NULL", []),
        ("ALTER TABLE t ADD PRIMARY KEY (id)", []),
        ("ALTER TABLE t ADD UNIQUE (a) NOT NULL", []),
        ("ALTER TABLE t ADD CHECK (a > 0)", []),
        ("ALTER TABLE t ADD INDEX ix (a) NOT NULL", []),
        ("ALTER TABLE t ADD c AS (a + 1) PERSISTED NOT NULL", []),
        # a multi-clause ALTER is one statement
        ("ALTER TABLE t ALTER COLUMN x TYPE bigint, ADD COLUMN c int NOT NULL;", [1]),
        (
            "ALTER TABLE t ADD COLUMN a int, ALTER COLUMN b DROP DEFAULT, ADD COLUMN c int NOT NULL;",
            [1],
        ),
        (
            "ALTER TABLE t ADD COLUMN a int NOT NULL DEFAULT 0, ALTER COLUMN b DROP DEFAULT;",
            [],
        ),
        ("ALTER TABLE t ALTER b DROP DEFAULT, ADD c int NOT NULL;", [1]),
        # T-SQL comma list after one ADD
        ("ALTER TABLE t ADD a int NULL, b int NOT NULL;", [1]),
        ("ALTER TABLE t ADD a int NULL, b int NOT NULL DEFAULT 0;", []),
        ("ALTER TABLE t ADD a int NOT NULL DEFAULT 0, b int NOT NULL;", [1]),
        ("ALTER TABLE t ADD a int NULL, DROP COLUMN b;", []),
        # keywords as column names
        ("ALTER TABLE devices ADD COLUMN serial varchar(32) NOT NULL;", [1]),
        ("ALTER TABLE devices ADD serial varchar(32) NOT NULL;", [1]),
        ("ALTER TABLE t ADD COLUMN identity_no int NOT NULL;", [1]),
        ("ALTER TABLE t ADD COLUMN period int NOT NULL;", [1]),
        ("ALTER TABLE t ADD period int NOT NULL;", [1]),
        ('ALTER TABLE t ADD COLUMN "check" int NOT NULL;', [1]),
        ('ALTER TABLE t ADD COLUMN "default" int NOT NULL;', [1]),
        ("ALTER TABLE s.t ADD COLUMN IF NOT EXISTS c int NOT NULL;", [1]),
        ("ALTER TABLE t ADD c int NOT NULL\nALTER TABLE u ADD d int DEFAULT 0", [1]),
        ("ALTER TABLE t ADD c int NOT NULL\nGO\nSELECT 1 AS x", [1]),
    ],
)
def test_not_null_without_default_variants(stmt, lines):
    hits = scan_rule(stmt, "sql.ddl.not-null-without-default", "ansi")
    assert [h["line"] for h in hits] == lines


@pytest.mark.parametrize(
    ("stmt", "lines"),
    [
        ("ALTER TABLE t DROP qty;", [1]),
        ("ALTER TABLE s.t DROP qty;", [1]),
        ("ALTER TABLE t RENAME qty TO quantity;", [1]),
        ("ALTER TABLE t DROP COLUMN qty;", [1]),
        ("ALTER TABLE t ADD c int, DROP qty;", [1]),
        ("ALTER TABLE t DROP CONSTRAINT fk;", []),
        ("ALTER TABLE t DROP INDEX ix;", []),
        ("ALTER TABLE t DROP PRIMARY KEY;", []),
        ("ALTER TABLE t DROP IF EXISTS qty;", []),
        ("ALTER TABLE t DROP PERIOD FOR SYSTEM_TIME;", []),
        ("ALTER TABLE t RENAME TO u;", []),
        ("ALTER TABLE t RENAME CONSTRAINT a TO b;", []),
        ("ALTER TABLE t ALTER COLUMN c DROP DEFAULT;", []),
        ("ALTER TABLE t ALTER COLUMN c DROP NOT NULL;", []),
        ("DROP TABLE t;", []),
    ],
)
def test_breaking_column_change_variants(stmt, lines):
    hits = scan_rule(stmt, "sql.ddl.breaking-column-change", "ansi")
    assert [h["line"] for h in hits] == lines


def test_ddl_findings_can_be_suppressed_with_the_marker():
    sql = f"-- sql-review: ignore {INDEX}\nCREATE INDEX ix ON t (c);"
    assert scan_rule(sql, INDEX, "postgres") == []
