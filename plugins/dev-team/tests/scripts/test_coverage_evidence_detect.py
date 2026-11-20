"""Unit tests for scripts/coverage_evidence_detect.py: format detection by
content, and the exact reason strings for unusable evidence."""

from __future__ import annotations

import json
import sys

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "scripts"))

import coverage_evidence_detect as detect

COVERAGEPY_WITH_CONTEXTS = {
    "meta": {"show_contexts": True},
    "files": {"app.py": {"contexts": {"10": ["tests/test_a.py::test_x"]}}},
}
COVERAGEPY_NO_CONTEXTS = {"meta": {}, "files": {"app.py": {"executed_lines": [1, 2]}}}
ISTANBUL = {"/app/a.js": {"statementMap": {"0": {}}, "s": {"0": 1}}}
JACOCO = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<!DOCTYPE report PUBLIC "-//JACOCO//DTD Report 1.1//EN" "report.dtd">'
    '<report name="t"><package name="app"><sourcefile name="A.java"><line nr="1" mi="0" ci="1" mb="0" cb="0"/></sourcefile></package></report>'
)
JACOCO_ZERO = JACOCO.replace('ci="1"', 'ci="0"')
COBERTURA = (
    '<?xml version="1.0"?><coverage line-rate="1"><packages><package><classes>'
    '<class filename="a.py"><lines><line number="1" hits="1"/></lines></class>'
    "</classes></package></packages></coverage>"
)
COBERTURA_ZERO = COBERTURA.replace('hits="1"', 'hits="0"')
STRYKER = {
    "schemaVersion": "1",
    "files": {
        "a.js": {"mutants": [{"id": "1", "killedBy": ["t1"], "coveredBy": ["t1"]}]}
    },
}
STRYKER_NO_PER_TEST = {
    "schemaVersion": "1",
    "files": {"a.js": {"mutants": [{"id": "1"}]}},
}
# Shapes written by mutmut 3.8.1: mutants/mutmut-stats.json, and a per-file mutants/**/*.meta.
MUTMUT = {
    "tests_by_mangled_function_name": {"app.x_f": ["tests/test_app.py::test_f"]},
    "duration_by_test": {"tests/test_app.py::test_f": 0.0001},
    "function_hashes": {"app.x_f": "0bb596aeee44"},
}
MUTMUT_META = {
    "exit_code_by_key": {"app.x_f__mutmut_1": 1},
    "hash_by_function_name": {"x_f": "0bb596aeee44"},
}
MUTMUT_EMPTY_TEST_MAP = {"tests_by_mangled_function_name": {}, "function_hashes": {}}
COVERAGEPY_EMPTY_STATIC_CONTEXT = {
    "meta": {},
    "files": {"app.py": {"contexts": {"10": [""]}}},
}


def _file(tmp_path, name, content):
    path = tmp_path / name
    path.write_text(content if isinstance(content, str) else json.dumps(content))
    return str(path)


def test_coveragepy_json_with_contexts(tmp_path):
    r = detect.classify(
        "coverage", _file(tmp_path, "cov.json", COVERAGEPY_WITH_CONTEXTS)
    )
    assert (r["format"], r["reason"]) == ("coveragepy-json", None)


def test_detection_is_by_content_not_extension(tmp_path):
    r = detect.classify(
        "coverage", _file(tmp_path, "report.txt", COVERAGEPY_WITH_CONTEXTS)
    )
    assert r["format"] == "coveragepy-json"


def test_valid_coveragepy_json_without_contexts_reports_no_contexts(tmp_path):
    r = detect.classify("coverage", _file(tmp_path, "cov.json", COVERAGEPY_NO_CONTEXTS))
    assert (r["format"], r["reason"]) == (None, "no contexts")


def test_missing_path(tmp_path):
    r = detect.classify("coverage", str(tmp_path / "gone.json"))
    assert (r["format"], r["reason"]) == (None, "missing")


def test_truncated_json_is_malformed_with_the_parser_error(tmp_path):
    r = detect.classify(
        "coverage", _file(tmp_path, "cov.json", '{"meta": {"show_contexts": tr')
    )
    assert r["format"] is None and r["reason"].startswith("malformed: ")


def test_unrecognised_json(tmp_path):
    r = detect.classify("coverage", _file(tmp_path, "x.json", {"hello": "world"}))
    assert (r["format"], r["reason"]) == (None, "unrecognised format")


def test_per_test_istanbul_directory(tmp_path):
    (tmp_path / "t1.json").write_text(json.dumps(ISTANBUL))
    (tmp_path / "t2.json").write_text(json.dumps(ISTANBUL))
    r = detect.classify("coverage", str(tmp_path))
    assert (r["format"], r["reason"]) == ("istanbul-dir", None)


def test_per_test_cobertura_directory(tmp_path):
    (tmp_path / "t1.xml").write_text(COBERTURA)
    r = detect.classify("coverage", str(tmp_path))
    assert (r["format"], r["reason"]) == ("cobertura-dir", None)


def test_per_test_jacoco_directory(tmp_path):
    (tmp_path / "t1.xml").write_text(JACOCO)
    (tmp_path / "t2.xml").write_text(JACOCO)
    r = detect.classify("coverage", str(tmp_path))
    assert (r["format"], r["reason"]) == ("jacoco-dir", None)


def test_malformed_xml_in_jacoco_directory_is_malformed(tmp_path):
    (tmp_path / "t1.xml").write_text(JACOCO)
    (tmp_path / "t2.xml").write_text("<report><unclosed>")
    r = detect.classify("coverage", str(tmp_path))
    assert r["format"] is None and r["reason"].startswith("malformed: ")


def test_jacoco_mixed_with_cobertura_is_unrecognised(tmp_path):
    (tmp_path / "a.xml").write_text(JACOCO)
    (tmp_path / "b.xml").write_text(COBERTURA)
    r = detect.classify("coverage", str(tmp_path))
    assert (r["format"], r["reason"]) == (None, "unrecognised format")


def test_malformed_xml_in_cobertura_directory(tmp_path):
    (tmp_path / "t1.xml").write_text("<coverage><unclosed>")
    r = detect.classify("coverage", str(tmp_path))
    assert r["format"] is None and r["reason"].startswith("malformed: ")


@pytest.mark.parametrize("setup", ["empty", "mixed", "other-xml", "other-text"])
def test_unusable_directories_are_unrecognised(tmp_path, setup):
    if setup == "mixed":
        (tmp_path / "a.xml").write_text(COBERTURA)
        (tmp_path / "b.json").write_text(json.dumps(ISTANBUL))
    elif setup == "other-xml":
        (tmp_path / "a.xml").write_text("<root/>")
    elif setup == "other-text":
        (tmp_path / "a.txt").write_text("plain text")
    r = detect.classify("coverage", str(tmp_path))
    assert (r["format"], r["reason"]) == (None, "unrecognised format")


def test_stryker_report(tmp_path):
    r = detect.classify("mutation", _file(tmp_path, "mutation-report.json", STRYKER))
    assert (r["format"], r["reason"]) == ("stryker", None)


def test_stryker_without_per_test_data_reports_no_contexts(tmp_path):
    r = detect.classify("mutation", _file(tmp_path, "m.json", STRYKER_NO_PER_TEST))
    assert (r["format"], r["reason"]) == (None, "no contexts")


def test_mutmut_stats(tmp_path):
    r = detect.classify("mutation", _file(tmp_path, "m.json", MUTMUT))
    assert (r["format"], r["reason"]) == ("mutmut", None)


def test_mutation_kind_does_not_accept_a_coverage_file(tmp_path):
    r = detect.classify("mutation", _file(tmp_path, "c.json", COVERAGEPY_WITH_CONTEXTS))
    assert (r["format"], r["reason"]) == (None, "unrecognised format")


def test_cli_prints_one_json_object_and_exits_zero_for_unusable_paths(tmp_path, capsys):
    code = detect.main(["--kind", "coverage", str(tmp_path / "gone.json")])
    out = json.loads(capsys.readouterr().out)
    assert code == 0 and out["reason"] == "missing"


def test_mutmut_meta_file_has_no_per_test_data(tmp_path):
    r = detect.classify("mutation", _file(tmp_path, "m.meta", MUTMUT_META))
    assert (r["format"], r["reason"]) == (None, "no contexts")


def test_mutmut_stats_whose_functions_name_no_test_report_no_contexts(tmp_path):
    data = {"tests_by_mangled_function_name": {"app.x_f": []}}
    r = detect.classify("mutation", _file(tmp_path, "m.json", data))
    assert (r["format"], r["reason"]) == (None, "no contexts")


def test_mutmut_stats_with_an_empty_test_map_reports_no_contexts(tmp_path):
    r = detect.classify("mutation", _file(tmp_path, "m.json", MUTMUT_EMPTY_TEST_MAP))
    assert (r["format"], r["reason"]) == (None, "no contexts")


def test_coveragepy_with_only_the_empty_static_context_reports_no_contexts(tmp_path):
    r = detect.classify(
        "coverage", _file(tmp_path, "c.json", COVERAGEPY_EMPTY_STATIC_CONTEXT)
    )
    assert (r["format"], r["reason"]) == (None, "no contexts")


@pytest.mark.parametrize("kind", ["coverage", "mutation"])
@pytest.mark.parametrize(
    "content",
    [
        "<?xml version='1.0'?><report name='jacoco'/>",
        "mode: set\napp/a.go:1.1,2.2 1 1\n",
        "TN:\nSF:a.js\n",
    ],
)
def test_readable_non_json_files_are_unrecognised_not_malformed(
    tmp_path, kind, content
):
    r = detect.classify(kind, _file(tmp_path, "report.dat", content))
    assert (r["format"], r["reason"]) == (None, "unrecognised format")


def test_binary_file_is_unrecognised(tmp_path):
    path = tmp_path / "b.bin"
    path.write_bytes(b"\xff\xfe\x00")
    assert detect.classify("coverage", str(path))["reason"] == "unrecognised format"


def test_stray_dotfiles_in_a_per_test_directory_are_ignored(tmp_path):
    (tmp_path / "t1.xml").write_text(COBERTURA)
    (tmp_path / ".DS_Store").write_bytes(b"\x00\x00")
    r = detect.classify("coverage", str(tmp_path))
    assert (r["format"], r["reason"]) == ("cobertura-dir", None)


ISTANBUL_ZERO = {"/app/a.js": {"statementMap": {"0": {}}, "s": {"0": 0}}}
LCOV_HIT = "TN:\nSF:a.js\nDA:1,2\nend_of_record\n"
LCOV_ZERO = "TN:\nSF:a.js\nDA:1,0\nend_of_record\n"
V8_HIT = {"result": [{"url": "a.js", "functions": [{"ranges": [{"count": 1}]}]}]}
V8_ZERO = {"result": [{"url": "a.js", "functions": [{"ranges": [{"count": 0}]}]}]}


def _dir(tmp_path, files):
    for name, content in files.items():
        (tmp_path / name).write_text(
            content if isinstance(content, str) else json.dumps(content)
        )
    return str(tmp_path)


@pytest.mark.parametrize(
    "files,fmt",
    [
        ({"t1.json": ISTANBUL, "t2.json": ISTANBUL_ZERO}, "istanbul-dir"),
        ({"t1.info": LCOV_HIT, "t2.info": LCOV_ZERO}, "lcov-dir"),
        ({"t1.json": V8_HIT, "t2.json": V8_ZERO}, "v8-dir"),
    ],
)
def test_per_test_js_directories_with_hits(tmp_path, files, fmt):
    r = detect.classify("coverage", _dir(tmp_path, files))
    assert (r["format"], r["reason"]) == (fmt, None)


@pytest.mark.parametrize(
    "files",
    [{"t.json": ISTANBUL_ZERO}, {"t.info": LCOV_ZERO}, {"t.json": V8_ZERO}],
)
def test_js_directories_without_hits_report_no_contexts(tmp_path, files):
    r = detect.classify("coverage", _dir(tmp_path, files))
    assert (r["format"], r["reason"]) == (None, "no contexts")


@pytest.mark.parametrize(
    "name,content", [("c.json", ISTANBUL), ("c.info", LCOV_HIT), ("c.json", V8_HIT)]
)
def test_single_aggregate_js_file_reports_no_contexts(tmp_path, name, content):
    r = detect.classify("coverage", _file(tmp_path, name, content))
    assert (r["format"], r["reason"]) == (None, "no contexts")


def test_mixed_js_formats_in_one_directory_are_unrecognised(tmp_path):
    r = detect.classify(
        "coverage", _dir(tmp_path, {"a.json": ISTANBUL, "b.info": LCOV_HIT})
    )
    assert (r["format"], r["reason"]) == (None, "unrecognised format")


@pytest.mark.parametrize("zero", [JACOCO_ZERO, COBERTURA_ZERO])
def test_xml_directory_without_a_covered_line_reports_no_contexts(tmp_path, zero):
    r = detect.classify("coverage", _dir(tmp_path, {"t.xml": zero}))
    assert (r["format"], r["reason"]) == (None, "no contexts")


@pytest.mark.parametrize(
    "files",
    [
        {"a.json": ISTANBUL, "b.json": V8_HIT},
        {"a.json": V8_HIT, "b.info": LCOV_HIT},
    ],
)
def test_mixed_json_and_other_js_formats_are_unrecognised(tmp_path, files):
    r = detect.classify("coverage", _dir(tmp_path, files))
    assert (r["format"], r["reason"]) == (None, "unrecognised format")


def test_truncated_json_in_a_js_directory_is_malformed(tmp_path):
    r = detect.classify("coverage", _dir(tmp_path, {"a.json": ISTANBUL, "b.json": '{"x": '}))
    assert r["format"] is None and r["reason"].startswith("malformed: ")


@pytest.mark.parametrize(
    "name,content,reason",
    [
        ("t.json", {"/a.js": {"statementMap": {}, "s": 5}}, "unrecognised format"),
        ("t.json", {"/a.js": {"statementMap": {}, "s": [1]}}, "unrecognised format"),
        ("t.json", {"result": []}, "unrecognised format"),
        ("t.json", {"result": [{"functions": None}]}, "no contexts"),
        ("t.json", {"result": [{"functions": [{"ranges": [{"count": "x"}]}]}]}, "no contexts"),
        ("t.info", "TN:\nSF:a.js\nDA:1,\u00b2\nend_of_record\n", "no contexts"),
    ],
)
def test_wrong_typed_js_report_values_are_unusable_not_a_crash(tmp_path, name, content, reason):
    r = detect.classify("coverage", _dir(tmp_path, {name: content}))
    assert (r["format"], r["reason"]) == (None, reason)


def test_lcov_like_text_without_end_of_record_is_unrecognised(tmp_path):
    r = detect.classify("coverage", _dir(tmp_path, {"t.info": "SF:a.js\nDA:1,1\n"}))
    assert (r["format"], r["reason"]) == (None, "unrecognised format")
