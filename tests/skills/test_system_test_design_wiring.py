"""The skills and agent that hand multi-deployable work to system-test-design
name it, and /test-health accepts and forwards --repos."""

from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[2] / "plugins" / "dev-team"


def _read(rel: str) -> str:
    return (PLUGIN / rel).read_text(encoding="utf-8")


def test_test_health_accepts_repos_and_invokes_system_test_design() -> None:
    text = _read("skills/test-health/SKILL.md")
    assert "--repos <path>..." in text.split("---", 2)[1]
    assert "`system-test-design`" in text.split("### 4. Delegate architecture")[1].split("### 5.")[0]
    assert "System-level test design (via system-test-design)" in text


def test_design_skills_flag_the_system_test_design_seam() -> None:
    for rel in ("skills/test-design/SKILL.md", "skills/test-design-advisor/SKILL.md"):
        assert "→ system-test-design" in _read(rel), rel


def test_existing_cd_test_architecture_seam_marker_is_unchanged() -> None:
    assert "→ cd-test-architecture" in _read("skills/test-design-advisor/SKILL.md")


def test_qa_engineer_routes_to_system_test_design() -> None:
    text = _read("agents/qa-engineer.md")
    assert "  - system-test-design\n" in text
    assert "`system-test-design` skill |" in text
    assert "`system-test-design` > `cd-test-architecture`" in text
