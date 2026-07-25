"""Contract for gherkin-derive's failure-path coverage gate wiring (issue
#1420, Step 3.3).
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, grep

SKILL = PLUGIN_ROOT / "skills" / "gherkin-derive" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text()


def test_documents_running_the_failure_path_gate():
    assert "gherkin_failure_path_gate.py" in _text()


def test_scope_names_both_xunit_with_annotations_and_bdd_runner():
    text = _text()
    idx = text.find("gherkin_failure_path_gate.py")
    assert idx != -1, "gherkin_failure_path_gate.py mention not found in SKILL.md"
    window = text[max(0, idx - 600) : idx + 200]
    assert "xunit-with-annotations" in window
    assert "bdd-runner" in window
    assert grep(r"not.*bdd-runner.*only|unlike the pending-stub gate", window, ignore_case=True)
