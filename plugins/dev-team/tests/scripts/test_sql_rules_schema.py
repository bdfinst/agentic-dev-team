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
POSITIONAL = "sql.schema.positional-insert"


def detect(stmt):
    return sql_scan.scan_text(stmt, "db/a.sql")


def count(stmt, rule):
    return sum(1 for f in detect(stmt) if f["rule"] == rule)


def rules_by_line(stmt):
    return [(f["line"], f["rule"]) for f in detect(stmt)]


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


# --- Scenario Outline: String.Format placeholders in the target name -------


@pytest.mark.parametrize(
    "stmt",
    [
        pytest.param("INSERT INTO FDTEMP_{0} SELECT * FROM t", id="suffix"),
        pytest.param("INSERT INTO {5}_WORKINGSET_{0} SELECT * FROM t", id="both-ends"),
        pytest.param("INSERT INTO dbo.{5}_ws SELECT * FROM t", id="after-dot"),
        pytest.param("INSERT INTO [dbo].FDTEMP_{0} SELECT * FROM t", id="after-quoted"),
    ],
)
def test_placeholder_target_is_one_insert_select_star_finding(stmt):
    assert [f["rule"] for f in detect(stmt)] == [INSERT_SELECT_STAR]


@pytest.mark.parametrize(
    "stmt",
    [
        pytest.param("INSERT INTO t_{0} VALUES (1)", id="values"),
        pytest.param("INSERT INTO {5}_WORKINGSET_{0} SELECT id FROM t", id="select"),
        pytest.param("INSERT INTO dbo.{5}_ws VALUES (1)", id="after-dot"),
    ],
)
def test_placeholder_target_without_column_list_is_positional(stmt):
    assert [f["rule"] for f in detect(stmt)] == [POSITIONAL]


@pytest.mark.parametrize(
    "stmt",
    [
        pytest.param("INSERT INTO FDTEMP_{0} (id) SELECT id FROM t", id="spaced"),
        pytest.param("INSERT INTO FDTEMP_{0}(id) SELECT id FROM t", id="no-space"),
    ],
)
def test_placeholder_target_with_column_list_is_clean(stmt):
    assert detect(stmt) == []


@pytest.mark.parametrize(
    ("stmt", "expected_text"),
    [
        pytest.param(
            "INSERT INTO dbo.{5}_ws SELECT id FROM t",
            "INSERT INTO dbo.{5}_ws SELECT",
            id="positional",
        ),
        pytest.param(
            "INSERT INTO {5}_WORKINGSET_{0} SELECT * FROM t",
            "INSERT INTO {5}_WORKINGSET_{0} SELECT *",
            id="insert-select-star",
        ),
    ],
)
def test_placeholder_target_is_shown_as_written(stmt, expected_text):
    assert [f["text"] for f in detect(stmt)] == [expected_text]


@pytest.mark.parametrize(
    "stmt",
    [
        pytest.param("INSERT INTO t {0} VALUES (1)", id="values"),
        pytest.param("INSERT INTO t {0} SELECT id FROM s", id="select"),
    ],
)
def test_placeholder_after_whitespace_is_not_part_of_the_name(stmt):
    assert detect(stmt) == []


@pytest.mark.parametrize(
    ("stmt", "expected_text"),
    [
        pytest.param(
            "INSERT INTO t_{abc} VALUES (1)", "INSERT INTO t_{abc} VALUES", id="named"
        ),
        pytest.param(
            "INSERT INTO {tableName} VALUES (1)",
            "INSERT INTO {tableName} VALUES",
            id="interpolated",
        ),
        pytest.param(
            "INSERT INTO t_{GetSuffix()} VALUES (1)",
            "INSERT INTO t_{GetSuffix()} VALUES",
            id="interpolated-call",
        ),
        pytest.param(
            "INSERT INTO t_{1.5} VALUES (1)", "INSERT INTO t_{1.5} VALUES", id="number"
        ),
        pytest.param(
            "INSERT INTO t_{0:N2} VALUES (1)",
            "INSERT INTO t_{0:N2} VALUES",
            id="format-spec",
        ),
        pytest.param(
            "INSERT INTO t_{0,10} VALUES (1)",
            "INSERT INTO t_{0,10} VALUES",
            id="alignment",
        ),
        pytest.param(
            "INSERT INTO t_{ 0} VALUES (1)",
            "INSERT INTO t_{ 0} VALUES",
            id="space-after-open",
        ),
        pytest.param(
            "INSERT INTO t_{0 } VALUES (1)",
            "INSERT INTO t_{0 } VALUES",
            id="space-before-close",
        ),
    ],
)
def test_any_one_line_brace_group_is_a_placeholder(stmt, expected_text):
    findings = detect(stmt)
    assert [(f["rule"], f["text"]) for f in findings] == [(POSITIONAL, expected_text)]


@pytest.mark.parametrize(
    "stmt",
    [
        pytest.param("INSERT INTO t_{\n0} VALUES (1)", id="line-break"),
        pytest.param("INSERT INTO t_{0 VALUES (1)", id="unclosed"),
        pytest.param("INSERT INTO t_{} VALUES (1)", id="empty"),
    ],
)
def test_malformed_brace_text_is_not_a_name_part(stmt):
    assert detect(stmt) == []


@pytest.mark.parametrize(
    ("stmt", "rule"),
    [
        pytest.param(
            "INSERT INTO {0} SELECT * FROM t", INSERT_SELECT_STAR, id="bare-star"
        ),
        pytest.param("INSERT INTO {0} VALUES (1)", POSITIONAL, id="bare-values"),
        pytest.param(
            "INSERT INTO {0}.dbo.t SELECT id FROM s", POSITIONAL, id="before-dot"
        ),
        pytest.param("INSERT INTO t_{10} VALUES (1)", POSITIONAL, id="two-digits"),
    ],
)
def test_placeholder_anywhere_in_the_name(stmt, rule):
    assert [f["rule"] for f in detect(stmt)] == [rule]


# --- Scenario Outline: column-less INSERT ... SELECT is positional -----------


@pytest.mark.parametrize(
    "stmt",
    [
        pytest.param("INSERT INTO archive SELECT id, name FROM orders", id="plain"),
        pytest.param("INSERT INTO archive (SELECT id FROM orders)", id="parenthesized"),
        pytest.param("INSERT INTO a ((SELECT id FROM b))", id="double-paren"),
        pytest.param(
            "INSERT INTO t WITH x AS (SELECT id FROM s) SELECT id FROM x", id="cte"
        ),
        pytest.param(
            "INSERT INTO t WITH x AS (SELECT id FROM s), y AS (SELECT id FROM x)"
            " SELECT id FROM y",
            id="two-ctes",
        ),
        pytest.param(
            "INSERT INTO t WITH x (a) AS (SELECT 1) SELECT a FROM x",
            id="cte-column-list",
        ),
        pytest.param(
            "INSERT INTO a SELECT x FROM b UNION ALL SELECT y FROM c", id="union"
        ),
        pytest.param(
            "INSERT INTO t SELECT a FROM s INTERSECT SELECT b FROM u", id="intersect"
        ),
        pytest.param(
            "INSERT INTO t SELECT a FROM s EXCEPT SELECT b FROM u", id="except"
        ),
        pytest.param("INSERT INTO t SELECT a FROM s MINUS SELECT b FROM u", id="minus"),
        pytest.param(
            "INSERT INTO t SELECT a FROM s UNION DISTINCT SELECT b FROM u",
            id="union-distinct",
        ),
        pytest.param("INSERT INTO t VALUE (1)", id="value-singular"),
        pytest.param(
            "INSERT INTO t OUTPUT inserted.value SELECT id FROM s",
            id="output-qualified-keyword-column",
        ),
        pytest.param("INSERT INTO t OUTPUT inserted.id SELECT id FROM s", id="output"),
        pytest.param("INSERT INTO t OUTPUT inserted.id VALUES (1)", id="output-values"),
        pytest.param("INSERT INTO archive AS a SELECT id FROM orders", id="alias"),
        pytest.param("INSERT INTO t WITH (TABLOCK) SELECT a FROM s", id="table-hint"),
        pytest.param("INSERT INTO t WITH (TABLOCK) VALUES (1)", id="table-hint-values"),
    ],
)
def test_insert_without_column_list_is_positional(stmt):
    assert [f["rule"] for f in detect(stmt)] == [POSITIONAL]


@pytest.mark.parametrize(
    "stmt",
    [
        pytest.param(
            "INSERT INTO archive (id, name) SELECT id, name FROM orders", id="plain"
        ),
        pytest.param(
            "INSERT INTO archive (id) (SELECT id FROM orders)", id="parenthesized"
        ),
        pytest.param("INSERT INTO a (id) ((SELECT id FROM b))", id="double-paren"),
        pytest.param(
            "INSERT INTO t (id) WITH x AS (SELECT id FROM s) SELECT id FROM x", id="cte"
        ),
        pytest.param(
            "INSERT INTO a (x) SELECT x FROM b UNION ALL SELECT y FROM c", id="union"
        ),
        pytest.param(
            "INSERT INTO t (id) OUTPUT inserted.id SELECT id FROM s", id="output"
        ),
        pytest.param(
            "INSERT INTO t (id) OUTPUT inserted.id VALUES (1)", id="output-values"
        ),
        pytest.param("INSERT INTO a AS x (id) SELECT id FROM b", id="alias"),
        pytest.param(
            "INSERT INTO t WITH (TABLOCK) (a) SELECT a FROM s", id="table-hint"
        ),
    ],
)
def test_insert_with_column_list_is_clean(stmt):
    assert detect(stmt) == []


@pytest.mark.parametrize(
    "stmt",
    [
        pytest.param(
            "INSERT INTO t WITH RECURSIVE x AS (SELECT 1) SELECT * FROM x",
            id="recursive-cte",
        ),
        pytest.param("INSERT INTO t OUTPUT inserted.id SELECT * FROM s", id="output"),
        pytest.param(
            "INSERT INTO t OUTPUT inserted.value SELECT * FROM s",
            id="output-qualified-keyword-column",
        ),
        pytest.param(
            "INSERT INTO t (id) OUTPUT deleted.Value SELECT * FROM s",
            id="output-qualified-keyword-column-with-list",
        ),
        pytest.param(
            "INSERT INTO t SELECT a FROM s EXCEPT (SELECT * FROM u)",
            id="except-parenthesized-branch",
        ),
        pytest.param("INSERT INTO t WITH (TABLOCK) SELECT * FROM s", id="table-hint"),
        pytest.param(
            "INSERT INTO t SELECT a FROM s UNION ALL (SELECT * FROM u)",
            id="parenthesized-union-branch",
        ),
        pytest.param(
            "INSERT INTO t SELECT a FROM s UNION ((SELECT * FROM u))",
            id="double-parenthesized-union-branch",
        ),
        pytest.param(
            "INSERT INTO t (SELECT a FROM s UNION (SELECT * FROM u))",
            id="union-inside-parenthesized-source",
        ),
        pytest.param(
            "INSERT INTO t (SELECT a FROM s) UNION (SELECT * FROM u)",
            id="union-after-parenthesized-branch",
        ),
        pytest.param(
            "INSERT INTO t ((SELECT a FROM s) UNION (SELECT * FROM u))",
            id="union-of-parenthesized-branches",
        ),
        pytest.param(
            "INSERT INTO t (a) (SELECT a FROM s) UNION (SELECT * FROM u)",
            id="union-after-column-list",
        ),
    ],
)
def test_star_in_any_source_branch_is_one_insert_select_star_finding(stmt):
    assert [f["rule"] for f in detect(stmt)] == [INSERT_SELECT_STAR]


@pytest.mark.parametrize(
    ("stmt", "expected"),
    [
        pytest.param(
            "INSERT INTO t OUTPUT inserted.id INTO @audit (id, value) SELECT id FROM s",
            [(POSITIONAL, "INSERT INTO t SELECT")],
            id="into-column-list",
        ),
        pytest.param(
            "INSERT INTO t OUTPUT inserted.id INTO @audit (id, value) VALUES (1)",
            [(POSITIONAL, "INSERT INTO t VALUES")],
            id="into-column-list-values",
        ),
        pytest.param(
            "INSERT INTO t OUTPUT inserted.id AS value SELECT * FROM s",
            [
                (
                    INSERT_SELECT_STAR,
                    "INSERT INTO t OUTPUT inserted.id AS value SELECT *",
                )
            ],
            id="alias",
        ),
        pytest.param(
            "INSERT INTO t OUTPUT inserted.id INTO @audit (id, value) SELECT * FROM s",
            [
                (
                    INSERT_SELECT_STAR,
                    "INSERT INTO t OUTPUT inserted.id INTO @audit ( id , value ) SELECT *",
                )
            ],
            id="into-column-list-star",
        ),
    ],
)
def test_keyword_inside_an_output_clause_does_not_end_it(stmt, expected):
    assert [(f["rule"], f["text"]) for f in detect(stmt)] == expected


@pytest.mark.parametrize(
    "stmt",
    [
        pytest.param(
            "MERGE INTO t USING s ON t.id = s.id\n"
            "WHEN NOT MATCHED THEN INSERT VALUES (s.id, s.name);",
            id="not-matched",
        ),
        pytest.param(
            "MERGE t USING s ON t.id = s.id\n"
            "WHEN NOT MATCHED BY TARGET THEN\nINSERT VALUES (s.id);",
            id="by-target",
        ),
    ],
)
def test_merge_insert_without_column_list_is_positional(stmt):
    findings = detect(stmt)
    assert [(f["rule"], f["text"]) for f in findings] == [(POSITIONAL, "INSERT VALUES")]
    assert findings[0]["line"] == stmt.count("\n", 0, stmt.index("INSERT")) + 1


@pytest.mark.parametrize(
    "stmt",
    [
        pytest.param(
            "MERGE INTO t USING s ON t.id = s.id\n"
            "WHEN NOT MATCHED THEN INSERT (id, name) VALUES (s.id, s.name);",
            id="column-list",
        ),
        pytest.param(
            "MERGE INTO t USING s ON t.id = s.id\n"
            "WHEN NOT MATCHED THEN INSERT DEFAULT VALUES;",
            id="default-values",
        ),
    ],
)
def test_merge_insert_with_column_list_is_clean(stmt):
    assert detect(stmt) == []


def test_insert_does_not_claim_a_select_after_its_statement_ends():
    stmt = "INSERT INTO t OUTPUT inserted.id;\nSELECT * FROM u"
    assert rules_by_line(stmt) == [(2, SELECT_STAR)]


def test_positional_text_names_the_target_and_source_keyword():
    stmt = "INSERT INTO t OUTPUT inserted.value SELECT id FROM s"
    assert [f["text"] for f in detect(stmt)] == ["INSERT INTO t SELECT"]


def test_deeply_nested_source_does_not_exhaust_the_stack():
    stmt = "INSERT INTO t " + "(" * 5000 + "SELECT 1"
    assert detect(stmt) == []


def test_parenthesized_source_ends_at_its_closing_paren():
    stmt = "INSERT INTO t (SELECT a FROM s)\nIF EXISTS (SELECT * FROM u) PRINT 1"
    assert [f["rule"] for f in detect(stmt)] == [POSITIONAL]


@pytest.mark.parametrize(
    ("stmt", "expected"),
    [
        pytest.param(
            "INSERT INTO t (a) SELECT a FROM s WHERE a IN (SELECT * FROM u)",
            [SELECT_STAR],
            id="in",
        ),
        pytest.param(
            "INSERT INTO t (a) SELECT a FROM s WHERE a > ALL (SELECT * FROM u)",
            [SELECT_STAR],
            id="all-quantifier",
        ),
        pytest.param(
            "INSERT INTO t SELECT a FROM s WHERE a > ALL (SELECT * FROM u)",
            [POSITIONAL, SELECT_STAR],
            id="all-quantifier-column-less",
        ),
        pytest.param(
            "INSERT INTO t SELECT x FROM (SELECT * FROM b) s",
            [POSITIONAL, SELECT_STAR],
            id="derived-table-column-less",
        ),
        pytest.param(
            "INSERT INTO t WITH x AS (SELECT * FROM s) SELECT id FROM x",
            [POSITIONAL, SELECT_STAR],
            id="cte-body-column-less",
        ),
    ],
)
def test_star_in_a_subquery_of_the_source_is_select_star(stmt, expected):
    assert [f["rule"] for f in detect(stmt)] == expected


def test_positional_cte_hit_is_on_the_insert_line():
    stmt = "INSERT INTO t\nWITH x AS (SELECT 1)\nSELECT a FROM x"
    assert rules_by_line(stmt) == [(1, POSITIONAL)]


def test_positional_select_hit_is_on_the_insert_line():
    stmt = "SELECT 1;\nINSERT INTO archive\nSELECT id FROM orders;"
    assert rules_by_line(stmt) == [(2, POSITIONAL)]


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


@pytest.mark.parametrize(
    ("stmt", "expected"),
    [
        pytest.param(
            "INSERT INTO a (x) SELECT x FROM b\nSELECT * FROM c",
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
            "INSERT INTO a (x) SELECT x FROM b\nGO\nSELECT * FROM c",
            [(3, SELECT_STAR)],
            id="select-after-go",
        ),
        pytest.param(
            "INSERT INTO a (x) SELECT x FROM b\nUPDATE t SET y = 1 WHERE id = 1\nSELECT * FROM c",
            [(3, SELECT_STAR)],
            id="select-after-update",
        ),
        pytest.param(
            "INSERT INTO a SELECT x FROM b UNION ALL SELECT * FROM c\nSELECT * FROM d",
            [(1, INSERT_SELECT_STAR), (2, SELECT_STAR)],
            id="union-then-new-statement",
        ),
        pytest.param(
            "INSERT INTO a SELECT x FROM b\nSELECT * FROM c",
            [(1, POSITIONAL), (2, SELECT_STAR)],
            id="select-after-positional-insert",
        ),
        pytest.param(
            "INSERT INTO a SELECT x FROM b\nGO\nSELECT * FROM c",
            [(1, POSITIONAL), (3, SELECT_STAR)],
            id="select-after-positional-insert-and-go",
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
    stmt = "INSERT INTO t (id) WITH x AS (SELECT id FROM s), y AS (SELECT id FROM x) SELECT id FROM y;"
    assert detect(stmt) == []


def test_star_inside_a_cte_of_an_insert_source_is_still_select_star():
    stmt = "INSERT INTO t (id) WITH x AS (SELECT * FROM s) SELECT id FROM x;"
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
