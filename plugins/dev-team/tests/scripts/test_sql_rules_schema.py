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
        ("SELECT * FROM orders", 1),
        ("SELECT o.* FROM orders o", 1),
        ("SELECT COUNT(*) FROM orders", 0),
        ("SELECT id FROM t WHERE EXISTS (SELECT * FROM u)", 0),
    ],
)
def test_select_star_boundaries(stmt, expected):
    assert count(stmt, SELECT_STAR) == expected


def test_select_star_reports_the_select_line():
    findings = detect("SELECT 1;\n\nSELECT *\nFROM orders;")
    assert [(f["rule"], f["line"]) for f in findings] == [(SELECT_STAR, 3)]


def test_select_star_hit_text_shows_the_star():
    assert detect("SELECT o.* FROM orders o")[0]["text"] == "SELECT o.*"


def test_select_star_is_suppressed_by_marker_for_that_rule_only():
    stmt = f"-- sql-review: ignore {SELECT_STAR}\nSELECT * FROM orders"
    assert detect(stmt) == []
    other = "-- sql-review: ignore sql.schema.ordinal-reference\nSELECT * FROM orders"
    assert [f["rule"] for f in detect(other)] == [SELECT_STAR]


# --- Scenario Outline: ordinal-reference boundaries --------------------------


@pytest.mark.parametrize(
    ("stmt", "expected"),
    [
        ("SELECT a, b FROM t ORDER BY 2", 1),
        ("SELECT a, COUNT(*) FROM t GROUP BY 1", 1),
        ("SELECT a FROM t ORDER BY created_at", 0),
        ("SELECT ROW_NUMBER() OVER (ORDER BY a) FROM t", 0),
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
