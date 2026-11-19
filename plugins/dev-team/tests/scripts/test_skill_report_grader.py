"""Unit tests for scripts/skill_report_grader.py.

Covers the count-target rule (a header table with current + recommended/target
columns; a sentence pairing a number, a test-type word, and a target word),
the fixture assertion grader, and the exit-code contract (0 pass, 1 fail,
2 did not run). The bad samples are the "fails on purpose" half of the gate:
a check that cannot fail would pass every report.
"""

from __future__ import annotations

import json
import sys

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "scripts"))

import skill_report_grader as grader

CURRENT_VS_RECOMMENDED = """## Shape

| Layer | Current | Recommended |
|---|---|---|
| unit | 40 | 120 |
"""

CURRENT_VS_TARGET = """| Type | current count | target count |
| --- | --- | --- |
| E2E | 30 | 5 |
"""


@pytest.mark.parametrize(
    "sentence",
    [
        "The suite should have 40 unit tests.",
        "We recommend 12 component tests for this service.",
        "Target: 5 E2E tests.",
        "Aim for a target of 3 contract tests per consumer.",
        "Recommend adding 8 integration tests.",
        "It should have an end-to-end suite of 4.",
    ],
)
def test_sentence_pairing_number_type_and_target_word_is_flagged(sentence: str) -> None:
    findings = grader.check_count_targets(sentence)
    assert findings
    assert findings[0].startswith("per-layer count target")


@pytest.mark.parametrize("table", [CURRENT_VS_RECOMMENDED, CURRENT_VS_TARGET])
def test_current_vs_recommended_table_is_flagged(table: str) -> None:
    findings = grader.check_count_targets(table)
    assert len(findings) == 1
    assert findings[0].startswith("current-vs-recommended table")


@pytest.mark.parametrize(
    "text",
    [
        "The service has 12 unit tests and 3 contract tests.",
        "| Suite | Path | Count |\n|---|---|---|\n| unit | tests/unit | 12 |",
        "| Test | Current | Class |\n|---|---|---|\n| a | x | KEEP |",
        "| Test | Class | Recommended action |\n|---|---|---|\n| a | KEEP | none |",
        "We recommend moving the retry check to a component test.",
        "## Recommended E2E candidates (max 10)",
        "The gap list is capped at 10 candidates.",
    ],
)
def test_descriptive_counts_and_unrelated_text_pass(text: str) -> None:
    assert grader.check_count_targets(text) == []


def test_count_target_inside_code_fence_is_ignored() -> None:
    text = "```\nThe suite should have 40 unit tests.\n```\n"
    assert grader.check_count_targets(text) == []


def test_grade_reports_each_unmet_assertion_kind() -> None:
    report = "# Report\n\n## Scope\n\nrepos: a, b\n\n## Overlap and misplacement\n\nnone\n"
    expected = {
        "sections_present": ["Scope", "System map"],
        "sections_absent": ["Overlap and misplacement"],
        "regex_present": [r"repos: a, b", r"discovered"],
        "regex_absent": [r"none", r"never matches"],
    }
    failures = grader.grade_report(report, expected)
    assert failures == [
        "section missing: System map",
        "section present but must be absent: Overlap and misplacement",
        "regex not found: discovered",
        "regex must be absent but matched: none",
    ]


def test_grade_passes_when_every_assertion_holds() -> None:
    report = "## Scope\n\nx\n"
    expected = {"sections_present": ["scope"], "regex_present": ["x"], "regex_absent": ["y"]}
    assert grader.grade_report(report, expected) == []


def test_headings_inside_code_fences_do_not_count() -> None:
    report = "```\n## System map\n```\n"
    assert grader.grade_report(report, {"sections_present": ["System map"]}) == [
        "section missing: System map"
    ]


def _write(tmp_path, name, content):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return str(path)


def test_cli_grade_exit_codes(tmp_path, capsys) -> None:
    report = _write(tmp_path, "r.md", "## Scope\n")
    ok = _write(tmp_path, "ok.json", json.dumps({"sections_present": ["Scope"]}))
    bad = _write(tmp_path, "bad.json", json.dumps({"sections_present": ["Nope"]}))
    broken = _write(tmp_path, "broken.json", "{not json")
    listy = _write(tmp_path, "list.json", "[]")

    assert grader.main(["grade", "--report", report, "--expected", ok]) == 0
    assert grader.main(["grade", "--report", report, "--expected", bad]) == 1
    assert grader.main(["grade", "--report", report, "--expected", broken]) == 2
    assert grader.main(["grade", "--report", report, "--expected", listy]) == 2
    assert grader.main(["grade", "--report", str(tmp_path / "gone.md"), "--expected", ok]) == 2
    capsys.readouterr()


def test_cli_count_targets_exit_codes(tmp_path, capsys) -> None:
    clean = _write(tmp_path, "clean.md", "The service has 12 unit tests.\n")
    dirty = _write(tmp_path, "dirty.md", CURRENT_VS_RECOMMENDED)

    assert grader.main(["count-targets", clean]) == 0
    assert grader.main(["count-targets", clean, dirty]) == 1
    assert grader.main(["count-targets", str(tmp_path / "gone.md")]) == 2
    out = capsys.readouterr().out
    assert "FAIL" in out and "current-vs-recommended table" in out


@pytest.mark.parametrize(
    "text",
    [
        "We recommend\n12 unit tests per service.",
        "Targets: 40 unit and 10 component tests.",
        "The suite should\nhave 5 contract tests... wait. It should have 5 contract tests.",
        "| Layer | Current | Recommendation |\n|---|---|---|\n| unit | 4 | 9 |",
        "| Layer | Current | Targets |\n|---|---|---|\n| unit | 4 | 9 |",
    ],
)
def test_wrapped_sentences_and_word_forms_are_flagged(text: str) -> None:
    assert grader.check_count_targets(text)


def test_table_inside_code_fence_is_ignored() -> None:
    assert grader.check_count_targets("```\n" + CURRENT_VS_RECOMMENDED + "```\n") == []


def test_validate_expected_rejects_unrunnable_shapes() -> None:
    assert grader.validate_expected({"sections_present": "Scope"})
    assert grader.validate_expected({"sections_present": [1]})
    assert grader.validate_expected({"regex_present": ["("]})
    assert grader.validate_expected({"sections_present": ["Scope"], "regex_absent": ["x"]}) is None


def test_cli_did_not_run_on_bad_expected_or_undecodable_report(tmp_path, capsys) -> None:
    report = _write(tmp_path, "r.md", "## Scope\n")
    bad_regex = _write(tmp_path, "re.json", json.dumps({"regex_present": ["("]}))
    bad_type = _write(tmp_path, "ty.json", json.dumps({"sections_present": "Scope"}))
    binary = tmp_path / "bin.md"
    binary.write_bytes(b"\xff\xfe\x00bad")
    ok = _write(tmp_path, "ok.json", json.dumps({}))

    assert grader.main(["grade", "--report", report, "--expected", bad_regex]) == 2
    assert grader.main(["grade", "--report", report, "--expected", bad_type]) == 2
    assert grader.main(["grade", "--report", str(binary), "--expected", ok]) == 2
    assert grader.main(["count-targets", str(binary)]) == 2
    capsys.readouterr()
