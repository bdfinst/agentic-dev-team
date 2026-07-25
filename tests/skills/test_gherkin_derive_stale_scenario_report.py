"""Contract for gherkin-derive's possibly-stale-scenario detection and report
(issue #1420, Step 2.2).
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, grep

SKILL = PLUGIN_ROOT / "skills" / "gherkin-derive" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text()


def test_documents_extracting_observed_value_and_calling_check_stale():
    text = _text()
    assert "check-stale" in text
    assert grep(r"observed condition|observed value", text, ignore_case=True)
    assert grep(r"deterministically|never.*eyeballing", text, ignore_case=True)


def test_documents_leaving_scenario_text_unmodified_on_mismatch():
    assert grep(r"leave.*unmodified|left unmodified", _text(), ignore_case=True)


def test_step6_has_distinct_possibly_stale_section_header():
    text = _text()
    idx = text.find('"possibly stale existing scenario"')
    assert idx != -1
    assert grep(r"never fold.*general summary|separately", text, ignore_case=True)


def test_report_line_format_names_file_line_asserted_and_observed():
    text = _text()
    assert grep(r"<file>:<line>", text)
    assert grep(r"asserts <X>|asserted value", text, ignore_case=True)
    assert grep(r"code now does <Y>|observed value", text, ignore_case=True)


def test_report_includes_verify_regressed_or_changed_instruction():
    text = _text()
    assert grep(r"verify whether.*regressed.*or.*changed", text, ignore_case=True)
