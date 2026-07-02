"""Contract for the /test-improve executive-summary template shipped with
the skill. Issue #536, Slice 10 Step 10.1.

Ported from tests/skills/test_improve_executive_summary_template_tests.bats
(issue #674).
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, grep

TEMPLATE = (
    PLUGIN_ROOT / "skills" / "test-improve" / "templates" / "executive-summary.md"
)


def _text() -> str:
    return TEMPLATE.read_text()


def test_executive_summary_template_exists():
    assert TEMPLATE.is_file()


def test_template_contains_all_10_numbered_section_headers():
    text = _text()
    assert grep(r"^## 1\. Bottom line", text)
    assert grep(r"^## 2\. What was done this run", text)
    assert grep(r"^## 3\. What was measured", text)
    assert grep(r"^## 4\. Findings from", text)
    assert grep(r"^## 5\. Work completed \(Phase 4 — no refactoring\)", text)
    assert grep(r"^## 6\. Work completed \(Phase 5 — refactor-for-testability\)", text)
    assert grep(r"^## 7\. Deferred work", text)
    assert grep(r"^## 8\. Waivers", text)
    assert grep(r"^## 9\. Next actions", text)
    assert grep(r"^## 10\. Provenance", text)


def test_template_1_carries_the_baseline_achieved_delta_metric_table_shape():
    text = _text()
    assert grep(r"baseline", text, ignore_case=True)
    assert grep(r"achieved|current", text, ignore_case=True)
    assert grep(r"delta|Δ|change", text, ignore_case=True)
    assert grep(r"\|", text)


def test_template_carries_the_go_advisory_footnote():
    text = _text()
    assert grep(r"go-mutesting.*alpha|alpha.*go-mutesting", text, ignore_case=True)
    assert grep(r"advisory", text, ignore_case=True)


def test_template_carries_the_mutation_disabled_placeholder_text():
    assert grep(
        r"mutation[[:space:]]+disabled|not[[:space:]]+applicable.*mutation",
        _text(),
        ignore_case=True,
    )


def test_template_carries_the_not_applicable_placeholder_for_empty_sections():
    assert grep(r"not[[:space:]]+applicable", _text(), ignore_case=True)
