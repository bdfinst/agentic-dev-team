"""Behavior of the SQL anti-pattern detector core (#2283).

One test (or one parametrized table) per Gherkin scenario in the issue. The
CLI scenarios run the script as a subprocess; the gate-failure scenario runs
``main`` in-process so it can inject an exception.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(SCRIPTS_DIR / "lib"))

import sql_anti_patterns
import sql_dialect
import sql_extract
import sql_rules
import sql_scan
from sql_tokenize import COMMENT, QUOTED, STRING, WORD, tokenize

CLI = SCRIPTS_DIR / "sql_anti_patterns.py"
RULE = "sql.schema.positional-insert"
MARKER = "-- sql-review: ignore sql.schema.positional-insert"


def run_cli(cwd, *args):
    proc = subprocess.run(
        [sys.executable, str(CLI), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def write(root, name, content):
    path = Path(root) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return name


def seed(root, content):
    return write(root, "db/seed.sql", content)


def scan(root, *names):
    code, out, err = run_cli(root, *names)
    return code, json.loads(out), err


def rule_hits(report):
    return [f for f in report["findings"] if f["rule"] == RULE]


# --- Scenario: Positional INSERT is flagged with message and fix -------------


def test_positional_insert_is_flagged_with_message_and_fix(tmp_path):
    seed(tmp_path, "SELECT 1;\n\nINSERT INTO orders VALUES (1, 'a')\n")
    code, report, _ = scan(tmp_path, "db/seed.sql")
    assert code == 0
    assert len(report["findings"]) == 1
    finding = report["findings"][0]
    assert finding["rule"] == RULE
    assert finding["line"] == 3
    assert finding["dialect"] == "ansi"
    assert finding["origin"] == "sql"
    assert finding["file"] == "db/seed.sql"
    assert finding["message"].strip()
    assert finding["fix"].strip()
    assert "\n" not in finding["message"] and "\n" not in finding["fix"]


def test_finding_message_and_fix_come_from_the_rule_entry(tmp_path):
    seed(tmp_path, "INSERT INTO t VALUES (1)")
    _, report, _ = scan(tmp_path, "db/seed.sql")
    rule = next(r for r in sql_rules.discover_rules() if r.id == RULE)
    assert report["findings"][0]["message"] == rule.message
    assert report["findings"][0]["fix"] == rule.fix
    assert report["findings"][0]["severity"] == rule.severity


# --- Scenario Outline: INSERT forms that are not positional ------------------


@pytest.mark.parametrize(
    "stmt",
    [
        "INSERT INTO orders (id, name) VALUES (1, 'a')",
        "insert into orders(id) values (1)",
        "INSERT INTO orders DEFAULT VALUES",
    ],
)
def test_insert_forms_that_are_not_positional(tmp_path, stmt):
    seed(tmp_path, stmt)
    _, report, _ = scan(tmp_path, "db/seed.sql")
    assert rule_hits(report) == []


# --- Scenario: Multi-row and lowercase positional INSERT ---------------------


def test_multi_row_lowercase_positional_insert(tmp_path):
    seed(tmp_path, "insert into t values (1), (2)")
    _, report, _ = scan(tmp_path, "db/seed.sql")
    assert [(f["rule"], f["line"]) for f in rule_hits(report)] == [(RULE, 1)]


@pytest.mark.parametrize(
    "stmt",
    [
        "INSERT INTO dbo.orders VALUES (1)",
        'INSERT INTO "my schema"."orders" VALUES (1)',
        "INSERT INTO [dbo].[orders] VALUES (1)",
        "INSERT orders VALUES (1)",
        "INSERT INTO orders AS o VALUES (1)",
        "INSERT INTO t\nVALUES\n(1)",
        "INSERT INTO t SELECT a, b FROM s",
        "INSERT INTO FDTEMP_{0} VALUES (1)",
    ],
)
def test_other_positional_spellings_fire(tmp_path, stmt):
    seed(tmp_path, stmt)
    _, report, _ = scan(tmp_path, "db/seed.sql")
    assert [f["line"] for f in rule_hits(report)] == [1]


@pytest.mark.parametrize(
    "stmt",
    [
        "CREATE TRIGGER trg AFTER INSERT ON t FOR EACH ROW EXECUTE FUNCTION f()",
        "GRANT INSERT ON t TO app",
        "INSERT INTO t (a, b) SELECT a, b FROM s",
    ],
)
def test_insert_keyword_without_values_does_not_fire(tmp_path, stmt):
    seed(tmp_path, stmt)
    _, report, _ = scan(tmp_path, "db/seed.sql")
    assert rule_hits(report) == []


# --- Scenario Outline: Comments and strings are lexed correctly --------------


@pytest.mark.parametrize(
    ("content", "count"),
    [
        ("-- INSERT INTO t VALUES (1)", 0),
        ("/* INSERT INTO t VALUES (1) */", 0),
        ("SELECT '-- not a comment'; INSERT INTO t VALUES (1)", 1),
        ("SELECT 'it''s'; INSERT INTO t VALUES (1)", 1),
        ("SELECT 'abc FROM t", 0),
    ],
)
def test_comments_and_strings_are_lexed_correctly(tmp_path, content, count):
    seed(tmp_path, content)
    code, report, _ = scan(tmp_path, "db/seed.sql")
    assert code == 0
    assert len(rule_hits(report)) == count


@pytest.mark.parametrize(
    "content",
    [
        "SELECT 'INSERT INTO t VALUES (1)'",
        "SELECT 'unterminated INSERT INTO t VALUES (1)",
        "/* unterminated INSERT INTO t VALUES (1)",
        'SELECT "INSERT INTO t VALUES (1)',
        "SELECT $$ INSERT INTO t VALUES (1) $$",
        "INSERT INTO t",
        "INSERT",
        "",
    ],
)
def test_unusual_text_gives_no_finding_and_no_crash(tmp_path, content):
    seed(tmp_path, content)
    code, report, err = scan(tmp_path, "db/seed.sql")
    assert code == 0
    assert report["findings"] == []
    assert err == ""


# --- Scenarios: suppression ---------------------------------------------------


def test_suppression_comment_on_the_line_before(tmp_path):
    seed(tmp_path, f"\n\n\n{MARKER}\nINSERT INTO t VALUES (1)\n")
    _, report, _ = scan(tmp_path, "db/seed.sql")
    assert [f for f in report["findings"] if f["line"] == 5] == []


def test_suppression_comment_on_the_same_line(tmp_path):
    seed(tmp_path, f"\n\n\n\nINSERT INTO t VALUES (1) {MARKER}\n")
    _, report, _ = scan(tmp_path, "db/seed.sql")
    assert [f for f in report["findings"] if f["line"] == 5] == []


def test_block_comment_marker_suppresses(tmp_path):
    seed(
        tmp_path,
        "/* sql-review: ignore sql.schema.positional-insert */\nINSERT INTO t VALUES (1)\n",
    )
    _, report, _ = scan(tmp_path, "db/seed.sql")
    assert report["findings"] == []


@pytest.mark.parametrize(
    "placement",
    [
        f"{MARKER}\n\n",
        "SELECT 'sql-review: ignore sql.schema.positional-insert'\n",
    ],
    ids=["two-lines-before", "inside-a-string"],
)
def test_suppression_that_must_not_apply(tmp_path, placement):
    # The marker sits on line 3 (two lines before) or line 4 (in a string);
    # the INSERT is always on line 5.
    if placement.startswith("--"):
        content = f"\n\n{MARKER}\n\nINSERT INTO t VALUES (1)\n"
    else:
        content = f"\n\n\n{placement}INSERT INTO t VALUES (1)\n"
    seed(tmp_path, content)
    _, report, _ = scan(tmp_path, "db/seed.sql")
    assert [(f["rule"], f["line"]) for f in report["findings"]] == [(RULE, 5)]


def test_suppression_naming_a_different_rule_does_not_suppress(tmp_path):
    seed(
        tmp_path,
        "\n\n\n-- sql-review: ignore sql.schema.select-star\nINSERT INTO t VALUES (1)\n",
    )
    _, report, _ = scan(tmp_path, "db/seed.sql")
    assert [(f["rule"], f["line"]) for f in report["findings"]] == [(RULE, 5)]


def _two_rules_hitting_line(line):
    def make(rule_id):
        return sql_rules.Rule(
            rule_id,
            "x",
            "ansi",
            "script",
            "warning",
            "m",
            "f",
            check=lambda ctx: [sql_rules.Hit(line, "x")],
        )

    return [make("sql.x.a"), make("sql.x.b")]


def test_suppression_names_only_its_rule_when_two_rules_hit_one_line():
    rules = _two_rules_hitting_line(2)
    findings = sql_scan.scan_text(
        "-- sql-review: ignore sql.x.a\nSELECT 1", "f.sql", rules=rules
    )
    assert [f["rule"] for f in findings] == ["sql.x.b"]


def test_suppression_marker_below_the_hit_does_not_suppress():
    rules = _two_rules_hitting_line(1)
    findings = sql_scan.scan_text(
        "SELECT 1\n-- sql-review: ignore sql.x.a", "f.sql", rules=rules
    )
    assert [f["rule"] for f in findings] == ["sql.x.a", "sql.x.b"]


# --- Scenario: Mixed valid and failing inputs ---------------------------------


def test_mixed_valid_and_failing_inputs(tmp_path):
    write(tmp_path, "a.sql", "INSERT INTO t VALUES (1)\n")
    write(tmp_path, "b.sql", "")
    (tmp_path / "c.sql").write_bytes(b"\xff\xfe\x00bad")
    code, report, err = scan(tmp_path, "a.sql", "b.sql", "c.sql", "d.sql")
    assert code == 2
    assert [(f["file"], f["rule"]) for f in report["findings"]] == [("a.sql", RULE)]
    assert len(report["errors"]) == 2
    assert report["errors"][0].startswith("cannot read c.sql: ")
    assert report["errors"][1].startswith("cannot read d.sql: ")
    assert all(len(e.split(": ", 1)[1]) > 0 for e in report["errors"])
    assert "Traceback" not in err


def test_a_directory_argument_is_a_per_file_error(tmp_path):
    (tmp_path / "dir.sql").mkdir()
    code, report, _ = scan(tmp_path, "dir.sql")
    assert code == 2
    assert report["errors"][0].startswith("cannot read dir.sql: ")


def test_files_that_the_detector_does_not_handle_are_ignored(tmp_path):
    write(tmp_path, "README.md", "INSERT INTO t VALUES (1)")
    code, report, _ = scan(tmp_path, "README.md", "missing.txt")
    assert code == 0
    assert report == {"findings": [], "errors": [], "skipped_fragments": {}}


def test_utf8_bom_is_tolerated(tmp_path):
    (tmp_path / "bom.sql").write_bytes(b"\xef\xbb\xbfINSERT INTO t VALUES (1)")
    code, report, _ = scan(tmp_path, "bom.sql")
    assert code == 0
    assert [f["line"] for f in report["findings"]] == [1]


def test_files_from_reads_paths_from_a_list_file(tmp_path):
    write(tmp_path, "a.sql", "INSERT INTO t VALUES (1)\n")
    write(tmp_path, "list.txt", "a.sql\n\nREADME.md\n")
    code, report, _ = scan(tmp_path, "--files-from", "list.txt")
    assert code == 0
    assert len(report["findings"]) == 1


# --- Gate mode ------------------------------------------------------------------


def gate(root, *names):
    code, out, err = run_cli(root, "--gate", *names)
    assert err == ""
    return code, json.loads(out)


def test_gate_reports_dispatch_true_with_hits_for_sql(tmp_path):
    write(tmp_path, "README.md", "# hi")
    seed(tmp_path, "INSERT INTO t VALUES (1)\n")
    code, report = gate(tmp_path, "README.md", "db/seed.sql")
    assert code == 0
    assert report["status"] == "ok"
    assert report["dispatch"] is True
    assert [(h["file"], h["rule"]) for h in report["hits"]] == [("db/seed.sql", RULE)]


def test_gate_reports_dispatch_false_without_sql(tmp_path):
    write(tmp_path, "README.md", "# hi")
    write(tmp_path, "src/app.ts", "export const x = 1")
    code, report = gate(tmp_path, "README.md", "src/app.ts")
    assert code == 0
    assert report["dispatch"] is False
    assert report["hits"] == []


def test_gate_dispatches_for_clean_sql_with_an_empty_hit_list(tmp_path):
    write(tmp_path, "db/clean.sql", "INSERT INTO t (a) VALUES (1);\n")
    code, report = gate(tmp_path, "db/clean.sql")
    assert code == 0
    assert report["dispatch"] is True
    assert report["hits"] == []
    assert report["skipped_fragments"] == {}


def test_gate_dispatches_for_an_empty_sql_file(tmp_path):
    write(tmp_path, "db/empty.sql", "")
    _, report = gate(tmp_path, "db/empty.sql")
    assert report["dispatch"] is True


def test_gate_surfaces_per_file_errors_without_failing(tmp_path):
    write(tmp_path, "db/a.sql", "INSERT INTO t VALUES (1)\n")
    (tmp_path / "db/c.sql").write_bytes(b"\xff\xfe")
    code, report = gate(tmp_path, "db/a.sql", "db/c.sql")
    assert code == 0
    assert report["status"] == "ok"
    assert report["dispatch"] is True
    assert [h["file"] for h in report["hits"]] == ["db/a.sql"]
    assert [e.startswith("cannot read db/c.sql: ") for e in report["errors"]] == [True]


def test_gate_dispatches_when_the_only_sql_file_is_unreadable(tmp_path):
    (tmp_path / "db").mkdir()
    (tmp_path / "db/c.sql").write_bytes(b"\xff\xfe")
    code, report = gate(tmp_path, "db/c.sql")
    assert code == 0
    assert report["dispatch"] is True
    assert report["hits"] == []
    assert len(report["errors"]) == 1


def test_gate_reports_an_internal_failure_as_status_error(monkeypatch, capsys):
    def boom(paths, dialect=None):
        raise RuntimeError("scanner exploded")

    monkeypatch.setattr(sql_scan, "scan_paths", boom)
    code = sql_anti_patterns.main(["--gate", "db/seed.sql"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert code == 0
    assert payload["status"] == "error"
    assert "scanner exploded" in payload["message"]
    assert "Traceback" not in captured.out + captured.err
    assert captured.err == ""


def test_gate_reports_an_unreadable_files_from_as_status_error(tmp_path):
    code, out, err = run_cli(tmp_path, "--gate", "--files-from", "nope.txt")
    assert code == 0
    assert json.loads(out)["status"] == "error"
    assert "Traceback" not in err


# --- Dialect plumbing -------------------------------------------------------------


def test_findings_carry_the_rule_dialect_tag_not_the_file_dialect(tmp_path):
    seed(tmp_path, "INSERT INTO t VALUES (1)")
    _, report, _ = scan(tmp_path, "--dialect", "tsql", "db/seed.sql")
    assert [f["dialect"] for f in report["findings"]] == ["ansi"]


def test_unknown_dialect_is_a_usage_error(tmp_path):
    code, _, err = run_cli(tmp_path, "--dialect", "oracle", "x.sql")
    assert code == 2
    assert "invalid choice" in err


def test_inference_defaults_to_ansi():
    assert sql_dialect.infer_dialect("x.sql", "SELECT 1") == "ansi"


def test_dialect_tagged_rules_fire_only_on_a_matching_dialect():
    def check(ctx):
        yield sql_rules.Hit(1, "x")

    def make(rule_id, dialect):
        return sql_rules.Rule(
            rule_id, "x", dialect, "script", "warning", "m", "f", check=check
        )

    rules = [
        make("sql.x.ansi", "ansi"),
        make("sql.x.pg", "postgres"),
        make("sql.x.ms", "tsql"),
    ]
    fired = {
        d: [f["rule"] for f in sql_scan.scan_text("x", "f.sql", d, rules)]
        for d in ("ansi", "tsql", "postgres")
    }
    assert fired["ansi"] == ["sql.x.ansi"]
    assert fired["tsql"] == ["sql.x.ansi", "sql.x.ms"]
    assert fired["postgres"] == ["sql.x.ansi", "sql.x.pg"]


def test_agent_owned_rules_never_run_in_the_detector():
    rule = sql_rules.Rule("sql.x.judge", "x", "ansi", "agent", "warning", "m", "f")
    assert sql_scan.scan_text("anything", "f.sql", rules=[rule]) == []


# --- Rule discovery -------------------------------------------------------------


def test_discovery_loads_every_sql_rules_module():
    ids = [r.id for r in sql_rules.discover_rules()]
    assert RULE in ids
    assert len(ids) == len(set(ids))


def test_discovery_rejects_a_duplicate_rule_id(tmp_path, monkeypatch):
    body = (
        "from sql_rules import Rule\n"
        "RULES = (Rule('sql.dup.same', 'dup', 'ansi', 'agent', 'warning', 'm', 'f'),)\n"
    )
    (tmp_path / "sql_rules_dup_one.py").write_text(body)
    (tmp_path / "sql_rules_dup_two.py").write_text(body)
    monkeypatch.syspath_prepend(str(tmp_path))
    with pytest.raises(ValueError, match="duplicate rule id sql.dup.same"):
        sql_rules.discover_rules(tmp_path)


# --- Embedded-source extension point -----------------------------------------------


def test_registered_extractor_is_scanned_and_counts_skipped(tmp_path, monkeypatch):
    def extract_py(text):
        return sql_extract.Extraction(
            (
                sql_extract.Fragment(
                    "INSERT INTO t VALUES (1)", line_offset=9, origin="embedded"
                ),
            ),
            skipped=2,
        )

    monkeypatch.setitem(sql_extract.EMBEDDED_EXTRACTORS, ".py", extract_py)
    write(tmp_path, "app.py", "x = 1")
    result = sql_scan.scan_paths([str(tmp_path / "app.py")])
    assert result.dispatch is True
    assert result.skipped_fragments == {str(tmp_path / "app.py"): 2}
    assert [(f["line"], f["origin"]) for f in result.findings] == [(10, "embedded")]


def test_a_skipped_only_extraction_still_counts_as_sql_present(tmp_path, monkeypatch):
    monkeypatch.setitem(
        sql_extract.EMBEDDED_EXTRACTORS,
        ".py",
        lambda text: sql_extract.Extraction((), skipped=1),
    )
    write(tmp_path, "app.py", "x = 1")
    assert sql_scan.scan_paths([str(tmp_path / "app.py")]).dispatch is True


# --- Tokenizer ------------------------------------------------------------------------


def kinds(text):
    return [(t.kind, t.text) for t in tokenize(text)]


def test_tokenizer_line_comment_ends_at_newline():
    tokens = tokenize("a -- c\nb")
    assert [(t.kind, t.line) for t in tokens] == [(WORD, 1), (COMMENT, 1), (WORD, 2)]


def test_tokenizer_block_comment_spans_lines_and_nests():
    tokens = tokenize("/* a\n/* b */\n c */ x")
    assert [(t.kind, t.line) for t in tokens] == [(COMMENT, 1), (WORD, 3)]


def test_tokenizer_string_escape_and_unterminated():
    assert kinds("'it''s'") == [(STRING, "'it''s'")]
    token = tokenize("'abc")[0]
    assert (token.kind, token.terminated) == (STRING, False)


def test_tokenizer_unterminated_comment_and_quoted_identifier():
    assert tokenize("/* open")[0].terminated is False
    assert tokenize('"open')[0].terminated is False


def test_tokenizer_quoted_identifiers():
    assert [t.kind for t in tokenize('"a""b" `c` [d e]')] == [QUOTED, QUOTED, QUOTED]


def test_tokenizer_bracket_without_close_on_the_line_is_punctuation():
    tokens = tokenize("[abc\ndef]")
    assert tokens[0].kind == "punct"


def test_tokenizer_dollar_quote_is_one_string():
    assert kinds("$tag$ a ' b $tag$ x") == [(STRING, "$tag$ a ' b $tag$"), (WORD, "x")]


def test_tokenizer_tracks_lines_after_multiline_string():
    tokens = tokenize("'a\nb' c")
    assert [(t.kind, t.line) for t in tokens] == [(STRING, 1), (WORD, 2)]


def test_tokenizer_crlf_counts_one_line_per_newline():
    assert [t.line for t in tokenize("a\r\nb\r\nc")] == [1, 2, 3]


def test_tokenizer_never_raises_on_odd_bytes():
    for text in [
        "\x00",
        "﻿",
        "$",
        "$$",
        "/",
        "-",
        "[",
        "]]",
        "'",
        "é'x",
        "a" * 5000 + "'",
    ]:
        tokens = tokenize(text)
        assert [t.text for t in tokens] == _slices_at(text, tokens), repr(text)


def _slices_at(text, tokens):
    """The text each token's ``line``/``col`` points at, ``len(token.text)`` long."""
    line_starts = [0] + [k + 1 for k, ch in enumerate(text) if ch == "\n"]
    slices = []
    for t in tokens:
        start = line_starts[t.line - 1] + t.col - 1
        slices.append(text[start : start + len(t.text)])
    return slices


def test_scan_reports_unreadable_files_from_as_a_file_error(tmp_path):
    code, out, _ = run_cli(tmp_path, "--files-from", str(tmp_path / "missing.txt"))
    assert code == 2
    payload = json.loads(out)
    assert payload["findings"] == []
    assert payload["errors"][0].startswith("cannot read ")


def test_files_from_strips_trailing_whitespace_on_paths(tmp_path):
    sql = tmp_path / "a.sql"
    sql.write_text("INSERT INTO t VALUES (1)\n")
    listing = tmp_path / "list.txt"
    listing.write_text(f"{sql} \n")
    _, out, _ = run_cli(tmp_path, "--files-from", str(listing))
    assert [f["rule"] for f in json.loads(out)["findings"]] == [
        "sql.schema.positional-insert"
    ]


def test_tsql_omitted_schema_part_is_still_positional(tmp_path):
    sql = tmp_path / "b.sql"
    sql.write_text("INSERT INTO db..t VALUES (1)\n")
    _, out, _ = run_cli(tmp_path, str(sql))
    assert len(json.loads(out)["findings"]) == 1


def test_marker_in_a_multi_line_block_comment_uses_the_marker_line(tmp_path):
    seed(
        tmp_path,
        "/* header\n -- sql-review: ignore sql.schema.positional-insert */\nINSERT INTO t VALUES (1)\n",
    )
    _, out, _ = run_cli(tmp_path, "db/seed.sql")
    assert json.loads(out)["findings"] == []


def test_marker_two_lines_above_a_block_comment_end_does_not_suppress(tmp_path):
    seed(
        tmp_path,
        "/* sql-review: ignore sql.schema.positional-insert\n\n */\n\nINSERT INTO t VALUES (1)\n",
    )
    _, out, _ = run_cli(tmp_path, "db/seed.sql")
    assert [f["line"] for f in json.loads(out)["findings"]] == [5]
