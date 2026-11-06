"""Behavior of embedded-SQL extraction (#2285).

One test (or one parametrized table) per Gherkin scenario in the issue, then
edge cases for the literal scanners and the SQL-shape definition.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(SCRIPTS_DIR / "lib"))

import sql_extract
import sql_literals
import sql_literals_c
import sql_scan
from sql_shape import is_sql_shaped

CLI = SCRIPTS_DIR / "sql_anti_patterns.py"
RULE = "sql.schema.positional-insert"
INSERT = "INSERT INTO t VALUES (?, ?)"
EXTS = ["py", "ts", "tsx", "js", "jsx", "cs", "java"]


def run_cli(cwd, *args):
    proc = subprocess.run(
        [sys.executable, str(CLI), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, json.loads(proc.stdout), proc.stderr


def write(root, name, content):
    path = Path(root) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return name


def lines_with(line_no, content):
    """Source text that puts ``content`` on 1-based line ``line_no``."""
    return "\n" * (line_no - 1) + content + "\n"


def single(ext, sql):
    if ext == "py":
        return f'q = "{sql}"'
    if ext == "cs":
        return f'var q = "{sql}";'
    if ext == "java":
        return f'String q = "{sql}";'
    return f'const q = "{sql}";'


def hits(report):
    return [(f["line"], f["rule"], f["origin"]) for f in report["findings"]]


# --- Scenario: Positional INSERT in a single-line literal ----------------------------


@pytest.mark.parametrize("ext", EXTS)
def test_positional_insert_in_a_single_line_literal(tmp_path, ext):
    name = write(tmp_path, f"src/Repo.{ext}", lines_with(7, single(ext, INSERT)))
    code, report, _ = run_cli(tmp_path, name)
    assert code == 0
    assert hits(report) == [(7, RULE, "embedded")]
    assert report["findings"][0]["file"] == name


# --- Scenario: Multi-line literal forms report the INSERT keyword's line ---------------

MULTILINE = {
    ("py", "triple-quoted"): 'q = """\nINSERT INTO t VALUES (?, ?)\n"""',
    ("ts", "template"): "const q = `\nINSERT INTO t VALUES (?, ?)\n`;",
    ("cs", "verbatim"): 'var q = @"\nINSERT INTO t VALUES (?, ?)\n";',
    ("cs", "raw"): 'var q = """\nINSERT INTO t VALUES (?, ?)\n""";',
    ("java", "text-block"): 'String q = """\nINSERT INTO t VALUES (?, ?)\n""";',
}


@pytest.mark.parametrize(("ext", "form"), list(MULTILINE))
def test_multi_line_literal_reports_the_keyword_line(tmp_path, ext, form):
    name = write(tmp_path, f"src/Repo.{ext}", lines_with(10, MULTILINE[(ext, form)]))
    code, report, _ = run_cli(tmp_path, name)
    assert code == 0
    assert hits(report) == [(11, RULE, "embedded")]


@pytest.mark.parametrize("ext", ["py", "ts", "cs", "java"])
def test_keyword_on_the_opening_line_of_a_multi_line_literal(tmp_path, ext):
    body = {
        "py": 'q = """INSERT INTO t VALUES (?)\n"""',
        "ts": "const q = `INSERT INTO t VALUES (?)\n`;",
        "cs": 'var q = @"INSERT INTO t VALUES (?)\n";',
        "java": 'String q = """INSERT INTO t VALUES (?)\n""";',
    }[ext]
    name = write(tmp_path, f"a.{ext}", lines_with(4, body))
    _, report, _ = run_cli(tmp_path, name)
    assert hits(report) == [(4, RULE, "embedded")]


def test_a_second_literal_after_a_multi_line_one_keeps_its_line(tmp_path):
    src = 'a = """\nx\ny"""\nb = "INSERT INTO t VALUES (?)"\n'
    name = write(tmp_path, "a.py", src)
    _, report, _ = run_cli(tmp_path, name)
    assert hits(report) == [(4, RULE, "embedded")]


# --- Scenario: Keyword-leading prose is not SQL ----------------------------------------

PROSE = [
    "Select an option from the list",
    "Insert into the form the values (a, b)",
    "Update your profile settings",
]


@pytest.mark.parametrize("text", PROSE)
def test_keyword_leading_prose_is_not_sql(tmp_path, text):
    name = write(tmp_path, "src/ui.py", f'label = "{text}"\n')
    code, report, _ = run_cli(tmp_path, name)
    assert (code, report["findings"], report["skipped_fragments"]) == (0, [], {})


@pytest.mark.parametrize(
    "text",
    PROSE
    + [
        "Select options from the list",
        "Delete from the cart now",
        "Create table of contents",
        "Alter table of contents",
        "SELECT 1",
        "hello",
        "",
    ],
)
def test_shape_rejects_prose(text):
    assert is_sql_shaped(text) is False


@pytest.mark.parametrize(
    "text",
    [
        "INSERT INTO t VALUES (?, ?)",
        "  \n insert into t(a) values (?)",
        "INSERT INTO t SELECT * FROM u",
        "SELECT name FROM users WHERE id = ?",
        "select * from t",
        "SELECT a, b.c, COUNT(*) AS n FROM orders o JOIN p ON 1 = 1",
        "SELECT DISTINCT a FROM (SELECT a FROM t) x",
        "UPDATE users u SET name = ?",
        "DELETE FROM t WHERE id = ?",
        "WITH x AS (SELECT 1) SELECT * FROM x",
        "ALTER TABLE t ADD COLUMN a int",
        "CREATE TABLE t (a int)",
        "CREATE UNIQUE INDEX i ON t (a)",
        "CREATE OR REPLACE VIEW v AS SELECT 1",
        "-- note\nINSERT INTO t VALUES (1)",
        "SELECT id FROM ${table} WHERE x = 1",
    ],
)
def test_shape_accepts_sql(text):
    assert is_sql_shaped(text) is True


def test_shape_is_linear_on_pathological_input():
    for text in (
        "SELECT " + "a, " * 5000 + "x",
        "SELECT " + "(" * 5000,
        "INSERT INTO " + "a." * 5000,
    ):
        assert is_sql_shaped(text) is False


# --- Scenario: Commented-out embedded SQL is ignored -----------------------------------

COMMENTED = {
    "py": '# q = "INSERT INTO t VALUES (1)"\nx = 1\n',
    "ts": '// const q = "INSERT INTO t VALUES (1)";\nconst x = 1;\n',
    "cs": '/* var q = "INSERT INTO t VALUES (1)"; */\nvar x = 1;\n',
    "java": '// String q = "INSERT INTO t VALUES (1)";\nint x = 1;\n',
}


@pytest.mark.parametrize("ext", sorted(COMMENTED))
def test_commented_out_embedded_sql_is_ignored(tmp_path, ext):
    name = write(tmp_path, f"src/a.{ext}", COMMENTED[ext])
    code, report, _ = run_cli(tmp_path, name)
    assert (code, report["findings"], report["skipped_fragments"]) == (0, [], {})
    gate_code, gate, _ = run_cli(tmp_path, "--gate", name)
    assert (gate_code, gate["dispatch"]) == (0, False)


@pytest.mark.parametrize(
    ("ext", "src"),
    [
        ("ts", '/* multi\nline "INSERT INTO t VALUES (1)" */\n'),
        ("java", '/** javadoc\n * "INSERT INTO t VALUES (1)"\n */\n'),
        ("cs", '// "INSERT INTO t VALUES (1)"\n'),
        ("js", 'const re = /"/; // "INSERT INTO t VALUES (1)"\n'),
    ],
)
def test_more_comment_forms_hide_sql(tmp_path, ext, src):
    name = write(tmp_path, f"a.{ext}", src)
    _, report, _ = run_cli(tmp_path, name)
    assert report["findings"] == []


# --- Scenario: Apostrophe in a comment does not corrupt later literals ------------------


def test_apostrophe_in_a_comment_does_not_corrupt_later_literals(tmp_path):
    src = "// don't\nconst q = 'INSERT INTO t VALUES (?)';\n"
    name = write(tmp_path, "src/a.ts", src)
    _, report, _ = run_cli(tmp_path, name)
    assert hits(report) == [(2, RULE, "embedded")]


@pytest.mark.parametrize(
    ("ext", "src"),
    [
        ("py", "# don't\nq = 'INSERT INTO t VALUES (?)'\n"),
        ("cs", '// don\'t\nvar q = "INSERT INTO t VALUES (?)";\n'),
        ("java", '/* don\'t */\nString q = "INSERT INTO t VALUES (?)";\n'),
        ("jsx", "const a = <p>don't</p>;\nconst q = 'INSERT INTO t VALUES (?)';\n"),
    ],
)
def test_apostrophes_elsewhere_do_not_corrupt_later_literals(tmp_path, ext, src):
    name = write(tmp_path, f"a.{ext}", src)
    _, report, _ = run_cli(tmp_path, name)
    assert hits(report) == [(2, RULE, "embedded")]


def test_a_char_literal_quote_does_not_open_a_string(tmp_path):
    src = 'char c = \'"\';\nString q = "INSERT INTO t VALUES (?)";\n'
    name = write(tmp_path, "A.java", src)
    _, report, _ = run_cli(tmp_path, name)
    assert hits(report) == [(2, RULE, "embedded")]


def test_a_regex_literal_quote_does_not_open_a_string(tmp_path):
    src = "const re = /[\"']/g;\nconst q = 'INSERT INTO t VALUES (?)';\n"
    name = write(tmp_path, "a.js", src)
    _, report, _ = run_cli(tmp_path, name)
    assert hits(report) == [(2, RULE, "embedded")]


# --- Scenario: Concatenated and interpolated literals are skipped and counted ------------


def test_concatenated_and_interpolated_literals_are_skipped_and_counted(tmp_path):
    src = (
        'query = "SELECT name FROM users WHERE id = \'" + user_id\n'
        'q2 = f"INSERT INTO t VALUES ({x})"\n'
    )
    name = write(tmp_path, "src/a.py", src)
    code, report, _ = run_cli(tmp_path, name)
    assert code == 0
    assert report["findings"] == []
    assert report["skipped_fragments"] == {name: 2}


@pytest.mark.parametrize(
    ("ext", "src"),
    [
        ("py", 'q = "SELECT a FROM t WHERE id = " + str(i)\n'),
        ("py", 'q = "INSERT INTO t VALUES (%s)" % x\n'),
        ("py", 'q = "INSERT INTO t VALUES ({})".format(x)\n'),
        ("py", 'q += " INSERT INTO t VALUES (1)"\n'),
        ("py", 'q = ("SELECT a FROM t "\n     "WHERE id = 1")\n'),
        ("ts", "const q = `INSERT INTO t VALUES (${x})`;\n"),
        ("ts", 'const q = "SELECT a FROM t WHERE id = " + id;\n'),
        ("js", 'const q = id + "SELECT a FROM t WHERE id = 1";\n'),
        ("cs", 'var q = $"INSERT INTO t VALUES ({x})";\n'),
        ("cs", 'var q = "SELECT a FROM t WHERE id = " + id;\n'),
        ("java", 'String q = "SELECT a FROM t WHERE id = " + id;\n'),
    ],
)
def test_each_unscannable_form_is_counted_once(tmp_path, ext, src):
    name = write(tmp_path, f"a.{ext}", src)
    code, report, _ = run_cli(tmp_path, name)
    assert (code, report["findings"]) == (0, [])
    assert report["skipped_fragments"] == {name: 1}
    gate_code, gate, _ = run_cli(tmp_path, "--gate", name)
    assert (gate_code, gate["dispatch"], gate["hits"]) == (0, True, [])


def test_a_non_sql_concatenation_is_not_counted(tmp_path):
    name = write(tmp_path, "a.py", 'msg = "Select an option" + suffix\n')
    _, report, _ = run_cli(tmp_path, name)
    assert report["skipped_fragments"] == {}


# --- Scenarios: Gate dispatch ---------------------------------------------------------


def test_gate_dispatches_on_embedded_sql_even_with_no_hits(tmp_path):
    name = write(tmp_path, "src/Repo.py", 'q = "INSERT INTO t (a) VALUES (?)"\n')
    code, gate, _ = run_cli(tmp_path, "--gate", name)
    assert (code, gate["status"], gate["dispatch"], gate["hits"]) == (0, "ok", True, [])


def test_gate_does_not_dispatch_on_sql_free_source(tmp_path):
    ui = write(tmp_path, "src/ui.py", 'label = "Select an option from the list"\n')
    app = write(tmp_path, "src/app.ts", "export const n = 1;\n")
    code, gate, _ = run_cli(tmp_path, "--gate", ui, app)
    assert (code, gate["status"], gate["dispatch"], gate["hits"]) == (
        0,
        "ok",
        False,
        [],
    )


def test_gate_dispatch_counts_a_skipped_only_file(tmp_path):
    name = write(tmp_path, "a.py", 'q = f"DELETE FROM t WHERE id = {i}"\n')
    _, gate, _ = run_cli(tmp_path, "--gate", name)
    assert gate["dispatch"] is True


# --- Scenario: Injection and N+1 fixture yields no detector findings ----------------------

FIXTURE = REPO_ROOT / "evals" / "fixtures" / "sql-boundary-injection-loop.py"
EXPECTED = REPO_ROOT / "evals" / "expected" / "sql-boundary-injection-loop.json"


def test_injection_and_loop_fixture_yields_no_detector_findings():
    result = sql_scan.scan_paths([str(FIXTURE)])
    assert result.findings == []
    assert result.errors == []
    assert result.skipped_fragments == {str(FIXTURE): 1}
    assert result.dispatch is True


def test_injection_and_loop_fixture_has_both_boundary_patterns():
    text = FIXTURE.read_text(encoding="utf-8")
    assert "+ user_id +" in text  # concatenated query
    body = text.split("for user_id")[1]
    assert "SELECT id, total FROM orders WHERE user_id = ?" in body  # in the loop


def test_boundary_expected_json_expects_no_issues():
    spec = json.loads(EXPECTED.read_text(encoding="utf-8"))
    assert spec["fixture"] == FIXTURE.name
    assert (FIXTURE.parent / spec["fixture"]).is_file()
    assert spec["applicableAgents"] == ["sql-review"]
    agent = spec["agents"]["sql-review"]
    assert agent["expectedStatus"] == "pass"
    assert agent["issueCount"] == {"min": 0, "max": 0}
    assert agent["expectedFindings"] == []


# --- AC6: robustness -----------------------------------------------------------------------

UNTERMINATED = {
    "py": 'x = "abc\ny = 1\n',
    "ts": "const x = 'abc\nconst y = `abc\n",
    "cs": 'var x = "abc\nvar y = @"abc\n',
    "java": 'String x = "abc\nString y = """abc\n',
}


@pytest.mark.parametrize("ext", sorted(UNTERMINATED))
def test_unterminated_quotes_give_no_findings_and_no_crash(tmp_path, ext):
    name = write(tmp_path, f"a.{ext}", UNTERMINATED[ext])
    code, report, _ = run_cli(tmp_path, name)
    assert (code, report["findings"], report["errors"]) == (0, [], [])


def test_an_unterminated_quote_does_not_hide_a_later_line_in_c_family(tmp_path):
    name = write(
        tmp_path, "a.java", 'String x = "abc\nString q = "INSERT INTO t VALUES (?)";\n'
    )
    _, report, _ = run_cli(tmp_path, name)
    assert hits(report) == [(2, RULE, "embedded")]


def test_a_non_utf8_file_is_a_per_file_error_and_others_are_scanned(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_bytes(b'q = "INSERT INTO t VALUES (\xff)"\n')
    good = write(tmp_path, "good.py", 'q = "INSERT INTO t VALUES (?)"\n')
    code, report, _ = run_cli(tmp_path, "bad.py", good)
    assert code == 2
    assert hits(report) == [(1, RULE, "embedded")]
    assert len(report["errors"]) == 1 and "bad.py" in report["errors"][0]


@pytest.mark.parametrize("ext", EXTS)
def test_odd_input_never_raises(ext):
    extractor = sql_extract.EMBEDDED_EXTRACTORS["." + ext]
    for text in (
        "",
        '"',
        "'",
        '"""',
        "`",
        "${",
        "/*",
        '@"',
        '$@"',
        "\\",
        "\x00",
        "\n\n",
        "f'{",
        'f"{x',
    ):
        extractor(text)


def test_registered_suffixes():
    assert set(sql_extract.EMBEDDED_EXTRACTORS) == {f".{e}" for e in EXTS}


# --- Literal scanner details -----------------------------------------------------------------


def test_python_scanner_reports_body_line_and_flags():
    src = 'a = """\nx"""\nb = f"{y}"\nc = "p" + q\nd = "e"\n'
    got = [
        (lit.text, lit.line, lit.interpolated, lit.concatenated)
        for lit in sql_literals.python_literals(src)
    ]
    assert got == [
        ("\nx", 1, False, False),
        ("{y}", 3, True, False),
        ("p", 4, False, True),
        ("e", 5, False, False),
    ]


def test_python_f_string_without_a_field_is_scannable(tmp_path):
    name = write(tmp_path, "a.py", 'q = f"INSERT INTO t VALUES (?)"\n')
    _, report, _ = run_cli(tmp_path, name)
    assert hits(report) == [(1, RULE, "embedded")]


def test_template_literal_with_nested_template_is_interpolated():
    lits = sql_literals_c.js_literals("const q = `a ${`b ${c}`} d`;")
    assert [(lit.text, lit.interpolated) for lit in lits] == [("a ${`b ${c}`} d", True)]


def test_csharp_scanner_forms():
    src = 'var a = "x"; var b = @"y""z"; var c = $"{n}"; var d = """\nraw "q"\n""";'
    got = [(lit.text, lit.interpolated) for lit in sql_literals_c.csharp_literals(src)]
    assert got == [("x", False), ('y""z', False), ("{n}", True), ('\nraw "q"\n', False)]


def test_java_scanner_text_block_with_escaped_quotes():
    src = 'String a = """\n  say \\"""hi\\"""\n  """;'
    got = [lit.text for lit in sql_literals_c.java_literals(src)]
    assert got == ['\n  say \\"""hi\\"""\n  ']


def test_extraction_marks_fragments_embedded_with_zero_based_offset():
    extraction = sql_extract.extract("a.py", '\n\nq = "INSERT INTO t VALUES (1)"\n')
    assert extraction.fragments == (
        sql_extract.Fragment("INSERT INTO t VALUES (1)", 2, "embedded"),
    )
    assert extraction.skipped == 0
