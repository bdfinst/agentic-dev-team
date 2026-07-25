"""Contract for gherkin-derive's failure-path coverage gate wiring (issue
#1420, Step 3.3).
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, grep, section_outside_code

SKILL = PLUGIN_ROOT / "skills" / "gherkin-derive" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text()


def test_documents_running_the_failure_path_gate():
    assert "gherkin_failure_path_gate.py" in _text()


def test_scope_names_both_xunit_with_annotations_and_bdd_runner():
    # Anchored on the named headers around the failure-path-gate scope
    # statement (not a raw character-offset window, which was fragile:
    # tuned to today's prose length and would break spuriously on an
    # unrelated edit, or pass vacuously against an earlier unrelated
    # "xunit-with-annotations" mention if the prose shifted).
    text = _text()
    scope = section_outside_code(
        text,
        r"^\*\*Every mode that writes `\.feature` files",
        boundary_pattern=r"^## Key differences",
    )
    assert scope, "failure-path-gate scope section not found in gherkin-derive/SKILL.md"
    assert "xunit-with-annotations" in scope
    assert "bdd-runner" in scope
    assert grep(r"not.*bdd-runner.*only|unlike the pending-stub gate", scope, ignore_case=True)
