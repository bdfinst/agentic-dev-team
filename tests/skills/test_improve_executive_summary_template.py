"""Contract for the /test-improve executive-summary template shipped with
the skill. Issue #536, Slice 10 Step 10.1.

Ported from tests/skills/test_improve_executive_summary_template_tests.bats
(issue #674).
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, grep, section

TEMPLATE = (
    PLUGIN_ROOT / "skills" / "test-improve" / "templates" / "executive-summary.md"
)


def _section_7() -> str:
    return section(_text(), r"^## 7\.", boundary_pattern=r"^## ")


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
    assert grep(r"^## 5\. Work completed \(Phase 5 — no refactoring\)", text)
    assert grep(r"^## 6\. Work completed \(Phase 7 — refactor-for-testability\)", text)
    assert grep(
        r"^## 7\. Deferred work — areas requiring refactoring to add tests", text
    )
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


# --- §7 REFACTOR_REQUIRED foregrounding (issue #968) --------------------------


def test_section_7_carries_seam_behavior_risk_column_triad():
    s = _section_7()
    assert grep(r"seam", s, ignore_case=True)
    assert grep(r"behavior", s, ignore_case=True)
    assert grep(r"risk", s, ignore_case=True)
    assert grep(r"\|", s)


def test_section_7_scoped_not_applicable_fallback_is_preserved():
    """Scoped to §7's own text, not the whole template — a whole-template
    check would still pass if §7's own fallback line were deleted, since the
    not-applicable phrase already appears in §5/§6/§8."""
    assert grep(r"not[[:space:]]+applicable", _section_7(), ignore_case=True)


def test_template_still_has_exactly_10_numbered_section_headers():
    text = _text()
    headers = [line for line in text.splitlines() if line.startswith("## ")]
    assert len(headers) == 10


def test_template_baseline_provenance_is_report_opt_in_conditional():
    """#1126: an opt-in run's baselines live under reports/test-improve/, so
    the template's provenance strings must name that location conditionally
    rather than hard-coding memory/."""
    text = _text()
    assert grep(r"\{\{baseline_dir\}\}", text)
    assert grep(r"reports/test-improve/\{\{slug\}\}/", text)
    assert grep(r"opted in", text, ignore_case=True)
