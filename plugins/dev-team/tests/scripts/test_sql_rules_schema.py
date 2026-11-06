"""Behavior of the remaining schema-coupling rules (#2284).

One parametrized table per Gherkin scenario outline. Scenarios run the whole
detector (every registered rule) over ``db/a.sql`` and assert per-rule ids, so
the "exactly one finding" and "no findings" rows also prove that sibling rules
do not double-report. One test drives the CLI end to end.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR / "lib"))

import sql_scan

CLI = SCRIPTS_DIR / "sql_anti_patterns.py"
INSERT_SELECT_STAR = "sql.schema.insert-select-star"
SELECT_STAR = "sql.schema.select-star"
ORDINAL = "sql.schema.ordinal-reference"


def detect(stmt):
    return sql_scan.scan_text(stmt, "db/a.sql")


def count(stmt, rule):
    return sum(1 for f in detect(stmt) if f["rule"] == rule)


# --- Scenario: INSERT ... SELECT * reports one finding, not two -------------


def test_insert_select_star_reports_one_finding_not_two():
    findings = detect("INSERT INTO archive SELECT * FROM orders")
    assert [f["rule"] for f in findings] == [INSERT_SELECT_STAR]


def test_insert_select_star_cli_reports_exactly_one_finding(tmp_path):
    (tmp_path / "db").mkdir()
    (tmp_path / "db" / "a.sql").write_text(
        "INSERT INTO archive SELECT * FROM orders", encoding="utf-8"
    )
    proc = subprocess.run(
        [sys.executable, str(CLI), "db/a.sql"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert proc.stderr == ""
    report = json.loads(proc.stdout)
    assert [f["rule"] for f in report["findings"]] == [INSERT_SELECT_STAR]
    assert report["findings"][0]["line"] == 1


def test_insert_select_star_with_column_list_is_one_finding():
    findings = detect("INSERT INTO a (x, y) SELECT * FROM b")
    assert [f["rule"] for f in findings] == [INSERT_SELECT_STAR]


def test_insert_select_star_union_branch_is_one_finding():
    findings = detect("INSERT INTO a SELECT * FROM b UNION ALL SELECT * FROM c")
    assert [f["rule"] for f in findings] == [INSERT_SELECT_STAR]


def test_select_star_in_a_subquery_of_an_insert_source_is_still_reported():
    stmt = "INSERT INTO a (x) SELECT x FROM (SELECT * FROM b) s"
    assert [f["rule"] for f in detect(stmt)] == [SELECT_STAR]


# --- Scenario: INSERT with column list from named select is clean -----------


def test_insert_with_column_list_from_named_select_is_clean():
    assert detect("INSERT INTO a (x) SELECT x FROM b") == []


# --- Scenario Outline: select-star boundaries --------------------------------


@pytest.mark.parametrize(
    ("stmt", "expected"),
    [
        pytest.param("SELECT * FROM orders", 1, id="bare-star"),
        pytest.param("SELECT o.* FROM orders o", 1, id="qualified-star"),
        pytest.param("SELECT COUNT(*) FROM orders", 0, id="count-star"),
        pytest.param(
            "SELECT id FROM t WHERE EXISTS (SELECT * FROM u)", 0, id="exists-subquery"
        ),
    ],
)
def test_select_star_boundaries(stmt, expected):
    assert count(stmt, SELECT_STAR) == expected


def test_select_star_reports_the_select_line():
    findings = detect("SELECT 1;\n\nSELECT *\nFROM orders;")
    assert [(f["rule"], f["line"]) for f in findings] == [(SELECT_STAR, 3)]


def test_select_star_hit_text_shows_the_star():
    assert detect("SELECT o.* FROM orders o")[0]["text"] == "SELECT o.*"


def test_select_star_is_suppressed_by_its_own_marker():
    stmt = f"-- sql-review: ignore {SELECT_STAR}\nSELECT * FROM orders"
    assert detect(stmt) == []


def test_select_star_is_not_suppressed_by_another_rules_marker():
    stmt = f"-- sql-review: ignore {ORDINAL}\nSELECT * FROM orders"
    assert [f["rule"] for f in detect(stmt)] == [SELECT_STAR]


# --- Scenario Outline: ordinal-reference boundaries --------------------------


@pytest.mark.parametrize(
    ("stmt", "expected"),
    [
        pytest.param("SELECT a, b FROM t ORDER BY 2", 1, id="order-by-ordinal"),
        pytest.param("SELECT a, COUNT(*) FROM t GROUP BY 1", 1, id="group-by-ordinal"),
        pytest.param(
            "SELECT a FROM t ORDER BY created_at", 0, id="order-by-column-name"
        ),
        pytest.param(
            "SELECT ROW_NUMBER() OVER (ORDER BY a) FROM t", 0, id="window-order-by"
        ),
    ],
)
def test_ordinal_reference_boundaries(stmt, expected):
    assert count(stmt, ORDINAL) == expected


def test_ordinal_reference_reports_the_clause_line():
    findings = detect("SELECT a, b\nFROM t\nORDER BY 2 DESC;")
    assert [(f["rule"], f["line"]) for f in findings] == [(ORDINAL, 3)]


def test_ordinal_in_a_window_clause_is_not_reported():
    stmt = "SELECT ROW_NUMBER() OVER (PARTITION BY b ORDER BY 1) FROM t"
    assert count(stmt, ORDINAL) == 0


def test_group_by_and_order_by_ordinals_are_two_findings():
    stmt = "SELECT a, COUNT(*) FROM t GROUP BY 1 ORDER BY 2"
    assert count(stmt, ORDINAL) == 2


# --- Statement boundaries without a semicolon (T-SQL) ------------------------


def rules_by_line(stmt):
    return [(f["line"], f["rule"]) for f in detect(stmt)]


@pytest.mark.parametrize(
    ("stmt", "expected"),
    [
        pytest.param(
            "INSERT INTO a SELECT x FROM b\nSELECT * FROM c",
            [(2, SELECT_STAR)],
            id="select-after-named-insert",
        ),
        pytest.param(
            "INSERT INTO a SELECT * FROM b\nSELECT * FROM c",
            [(1, INSERT_SELECT_STAR), (2, SELECT_STAR)],
            id="select-after-star-insert",
        ),
        pytest.param(
            "INSERT INTO a EXEC p\nSELECT * FROM c",
            [(2, SELECT_STAR)],
            id="select-after-insert-exec",
        ),
        pytest.param(
            "INSERT INTO a SELECT x FROM b\nGO\nSELECT * FROM c",
            [(3, SELECT_STAR)],
            id="select-after-go",
        ),
        pytest.param(
            "INSERT INTO a SELECT x FROM b\nUPDATE t SET y = 1\nSELECT * FROM c",
            [(3, SELECT_STAR)],
            id="select-after-update",
        ),
        pytest.param(
            "INSERT INTO a SELECT x FROM b UNION ALL SELECT * FROM c\nSELECT * FROM d",
            [(1, INSERT_SELECT_STAR), (2, SELECT_STAR)],
            id="union-then-new-statement",
        ),
    ],
)
def test_insert_source_scan_stops_at_the_next_statement(stmt, expected):
    assert rules_by_line(stmt) == expected


def test_ordinal_list_stops_at_the_next_statement():
    stmt = "SELECT a FROM t ORDER BY a\nEXEC dbo.p 1, 2"
    assert count(stmt, ORDINAL) == 0


def test_ordinal_after_a_case_expression_in_the_list_is_still_found():
    stmt = "SELECT a FROM t ORDER BY CASE WHEN a > 1 THEN 1 END, 2"
    assert count(stmt, ORDINAL) == 1


# --- INSERT target and trigger headers ---------------------------------------


@pytest.mark.parametrize(
    "stmt",
    [
        pytest.param(
            "CREATE TRIGGER trg ON t AFTER INSERT, UPDATE AS SELECT * FROM inserted;",
            id="trigger-insert-comma",
        ),
        pytest.param(
            "CREATE TRIGGER trg ON t AFTER INSERT AS SELECT * FROM inserted;",
            id="trigger-insert-as",
        ),
        pytest.param(
            "CREATE TRIGGER trg BEFORE INSERT ON t SELECT * FROM inserted;",
            id="trigger-insert-on",
        ),
    ],
)
def test_insert_keyword_in_a_trigger_header_is_not_an_insert(stmt):
    assert [f["rule"] for f in detect(stmt)] == [SELECT_STAR]


# --- CTE and parenthesized sources -------------------------------------------


def test_insert_with_cte_source_star_is_one_insert_select_star_finding():
    stmt = "INSERT INTO t WITH x AS (SELECT id FROM s) SELECT * FROM x;"
    assert [f["rule"] for f in detect(stmt)] == [INSERT_SELECT_STAR]


def test_insert_with_two_ctes_and_named_source_is_clean():
    stmt = "INSERT INTO t WITH x AS (SELECT id FROM s), y AS (SELECT id FROM x) SELECT id FROM y;"
    assert detect(stmt) == []


def test_star_inside_a_cte_of_an_insert_source_is_still_select_star():
    stmt = "INSERT INTO t WITH x AS (SELECT * FROM s) SELECT id FROM x;"
    assert [f["rule"] for f in detect(stmt)] == [SELECT_STAR]


def test_parenthesized_insert_source_is_one_insert_select_star_finding():
    stmt = "INSERT INTO a (SELECT * FROM b)"
    assert [f["rule"] for f in detect(stmt)] == [INSERT_SELECT_STAR]


def test_parenthesized_source_after_a_column_list_is_one_finding():
    stmt = "INSERT INTO a (x, y) (SELECT * FROM b)"
    assert [f["rule"] for f in detect(stmt)] == [INSERT_SELECT_STAR]


# --- Ordinal scope: function calls vs subqueries -------------------------------


@pytest.mark.parametrize(
    "stmt",
    [
        pytest.param(
            "SELECT STRING_AGG((a)::text, ',' ORDER BY 1) FROM t;",
            id="aggregate-with-parenthesized-first-arg",
        ),
        pytest.param(
            "SELECT STRING_AGG((SELECT 1), ',' ORDER BY 1) FROM t;",
            id="aggregate-with-subquery-first-arg",
        ),
    ],
)
def test_aggregate_order_by_is_not_an_ordinal_reference(stmt):
    assert count(stmt, ORDINAL) == 0


@pytest.mark.parametrize(
    "stmt",
    [
        pytest.param("SELECT x FROM (SELECT a x FROM t ORDER BY 1) s", id="derived"),
        pytest.param("SELECT x FROM ((SELECT a x FROM t ORDER BY 1)) s", id="nested"),
        pytest.param(
            "SELECT id FROM t WHERE id IN (SELECT id FROM u ORDER BY 1)", id="in"
        ),
    ],
)
def test_subquery_order_by_ordinal_is_still_reported(stmt):
    assert count(stmt, ORDINAL) == 1
