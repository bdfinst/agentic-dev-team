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
    ],
)
def test_markers_in_comments_strings_and_lookalikes_do_not_count(text):
    assert sql_dialect.infer_dialect("db/m.sql", text_of(text)) == "ansi"


def test_inference_table_is_data_not_code():
    assert sql_dialect.KEYWORD_MARKERS["tsql"] >= {"NOLOCK", "NVARCHAR"}
    assert sql_dialect.KEYWORD_MARKERS["postgres"] >= {
        "RETURNING",
        "ILIKE",
        "SERIAL",
        "CONCURRENTLY",
    }


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


@pytest.mark.parametrize(("dialect", "rule", "stmt", "count"), BOUNDARIES)
def test_dialect_and_ddl_rule_boundaries(tmp_path, dialect, rule, stmt, count):
    findings = scan_cli(tmp_path, stmt, "--dialect", dialect)
    assert rule_ids(findings).count(rule) == count


@pytest.mark.parametrize(("dialect", "rule", "stmt", "count"), BOUNDARIES)
def test_boundaries_hold_in_process_with_the_rule_tag(dialect, rule, stmt, count):
    hits = scan_rule(stmt, rule, dialect)
    assert len(hits) == count
    for hit in hits:
        assert hit["line"] == 1 and hit["dialect"] == rule_dialect(rule)


def rule_dialect(rule_id):
    return {r.id: r.dialect for r in sql_scan.discover_rules()}[rule_id]


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
    findings = scan_cli(tmp_path, "CREATE INDEX ix ON t (c) RETURNING id")
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
        ("ALTER TABLE t ADD c int NOT NULL\nALTER TABLE u ADD d int DEFAULT 0", [1]),
        ("ALTER TABLE t ADD c int NOT NULL\nGO\nSELECT 1 AS x", [1]),
    ],
)
def test_not_null_without_default_variants(stmt, lines):
    hits = scan_rule(stmt, "sql.ddl.not-null-without-default", "ansi")
    assert [h["line"] for h in hits] == lines


def test_ddl_findings_can_be_suppressed_with_the_marker():
    sql = f"-- sql-review: ignore {INDEX}\nCREATE INDEX ix ON t (c);"
    assert scan_rule(sql, INDEX, "postgres") == []
