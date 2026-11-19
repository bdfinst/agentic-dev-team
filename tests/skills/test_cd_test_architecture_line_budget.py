"""Structural guard: cd-test-architecture/SKILL.md stays within its line
budget, and the sections moved out of it stay reachable from the steps that
use them."""

from skill_doc_helpers import PLUGIN_ROOT, section

SKILL_DIR = PLUGIN_ROOT / "skills" / "cd-test-architecture"
SKILL = SKILL_DIR / "SKILL.md"
REFERENCE = SKILL_DIR / "references" / "build-vs-document.md"
LINE_BUDGET = 180
CITATION = "references/build-vs-document.md"


def _text() -> str:
    return SKILL.read_text(encoding="utf-8")


def test_skill_md_is_within_line_budget():
    assert len(_text().splitlines()) <= LINE_BUDGET


def test_reference_exists_and_holds_the_moved_sections():
    text = REFERENCE.read_text(encoding="utf-8")
    assert "### 4b. Build-vs-document decision" in text
    assert "### Companion: test-double setup guide" in text


def test_step_4_cites_the_reference():
    step_4 = section(_text(), r"^### 4\. Recommend", boundary_pattern=r"^### 5\.")
    assert CITATION in step_4


def test_step_6_cites_the_reference():
    step_6 = section(_text(), r"^### 6\. Report", boundary_pattern=r"^## Output")
    assert CITATION in step_6


def test_integration_points_multi_deployable_systems_at_system_test_design():
    integration = section(_text(), r"^## Integration", boundary_pattern=r"^## ")
    assert "system-test-design" in integration
