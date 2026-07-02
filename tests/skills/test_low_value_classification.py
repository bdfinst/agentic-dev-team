"""Doc-shape contract for the LOW_VALUE gap classification (epic #443,
issue #431).

LOW_VALUE is the third gap class alongside NO_REFACTOR / REFACTOR_REQUIRED:
technically-feasible findings that deliver no signal, plus existing
low-value tests that should be removed because a higher-layer test already
covers the same low-complexity code. These tests guard the doc-only
invariants across the four artifacts the slice touches.

Ported from tests/skills/low_value_classification_tests.bats (issue #674).
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, grep

TEST_HEALTH = PLUGIN_ROOT / "skills" / "test-health" / "SKILL.md"
SPECS = PLUGIN_ROOT / "skills" / "specs" / "SKILL.md"
PLAN = PLUGIN_ROOT / "skills" / "plan" / "SKILL.md"
SMELL = PLUGIN_ROOT / "agents" / "test-smell-review.md"


# --- test-health: LOW_VALUE column + Recommended removals table -------------


def test_test_health_gap_table_documents_a_low_value_class():
    assert "LOW_VALUE" in TEST_HEALTH.read_text()


def test_test_health_has_a_recommended_removals_table():
    assert grep(r"Recommended removals", TEST_HEALTH.read_text(), ignore_case=True)


def test_test_health_recommended_removals_names_a_covering_test_and_rationale():
    # The table must carry the covering test + one-line rationale columns
    # so a reader knows why each removal is safe.
    assert grep(r"covering test", TEST_HEALTH.read_text(), ignore_case=True)


def test_test_health_low_value_definition_names_the_three_criteria():
    # No branching logic + no observable outcome + coverage already
    # provided.
    text = TEST_HEALTH.read_text()
    assert grep(r"no branch", text, ignore_case=True)
    assert grep(r"observable", text, ignore_case=True)
    assert grep(r"higher.(layer|level)", text, ignore_case=True)


# --- specs: LOW_VALUE is skip, not defer ------------------------------------


def test_specs_documents_low_value_classification():
    assert "LOW_VALUE" in SPECS.read_text()


def test_specs_low_value_is_skip_not_defer():
    # The instruction must say skip (not defer) so low-value work never
    # lingers as deferred backlog.
    assert grep(
        r"skip[^.]*not[^.]*defer|skip, not defer", SPECS.read_text(), ignore_case=True
    )


# --- plan: LOW_VALUE filtered into a Skipped section; gate rejects ----------


def test_plan_has_a_skipped_low_value_section():
    assert grep(
        r"Skipped \(low value\)|Skipped \(low.value\)",
        PLAN.read_text(),
        ignore_case=True,
    )


def test_plan_gate_rejects_any_slice_classified_low_value():
    text = PLAN.read_text()
    assert "LOW_VALUE" in text
    # And the rejection must be explicit.
    assert grep(r"reject", text, ignore_case=True)


# --- test-smell-review: redundant low-level test as a named warning smell ---


def test_test_smell_review_detects_redundant_low_level_tests_as_a_named_smell():
    assert grep(r"Redundant Low-Level Test", SMELL.read_text(), ignore_case=True)


def test_test_smell_review_redundant_low_level_smell_is_severity_warning_with_removal_action():
    text = SMELL.read_text()
    assert grep(r"Redundant Low-Level Test", text, ignore_case=True)
    assert grep(r"warning", text, ignore_case=True)
    assert grep(r"removal|remove", text, ignore_case=True)
