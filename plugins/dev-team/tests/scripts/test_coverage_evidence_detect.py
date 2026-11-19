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
ISTANBUL = {"/app/a.js": {"statementMap": {}, "s": {}}}
COBERTURA = '<?xml version="1.0"?><coverage line-rate="1"><packages/></coverage>'
STRYKER = {
    "schemaVersion": "1",
    "files": {"a.js": {"mutants": [{"id": "1", "killedBy": ["t1"], "coveredBy": ["t1"]}]}},
}
STRYKER_NO_PER_TEST = {"schemaVersion": "1", "files": {"a.js": {"mutants": [{"id": "1"}]}}}
MUTMUT = {"exit_code_by_key": {"app.x_f__mutmut_1": 1}}


def _file(tmp_path, name, content):
    path = tmp_path / name
    path.write_text(content if isinstance(content, str) else json.dumps(content))
    return str(path)


def test_coveragepy_json_with_contexts(tmp_path):
    r = detect.classify("coverage", _file(tmp_path, "cov.json", COVERAGEPY_WITH_CONTEXTS))
    assert (r["format"], r["reason"]) == ("coveragepy-json", None)


def test_detection_is_by_content_not_extension(tmp_path):
    r = detect.classify("coverage", _file(tmp_path, "report.txt", COVERAGEPY_WITH_CONTEXTS))
    assert r["format"] == "coveragepy-json"


def test_valid_coveragepy_json_without_contexts_reports_no_contexts(tmp_path):
    r = detect.classify("coverage", _file(tmp_path, "cov.json", COVERAGEPY_NO_CONTEXTS))
    assert (r["format"], r["reason"]) == (None, "no contexts")


def test_missing_path(tmp_path):
    r = detect.classify("coverage", str(tmp_path / "gone.json"))
    assert (r["format"], r["reason"]) == (None, "missing")


def test_truncated_json_is_malformed_with_the_parser_error(tmp_path):
    r = detect.classify("coverage", _file(tmp_path, "cov.json", '{"meta": {"show_contexts": tr'))
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
