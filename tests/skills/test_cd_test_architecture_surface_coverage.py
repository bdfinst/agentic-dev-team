"""Content-guard tests for `cd-test-architecture/SKILL.md`'s Step 1
surface-coverage gate wiring (issue #1464).

Mirrors `tests/skills/test_gherkin_derive_skill.py`'s
`test_step_6_reports_analysis_coverage_gate_outcomes` pattern (issue #1450)
for cd-test-architecture's own `### Components & patterns` (H3)
configuration of the same (now-parameterized)
`gherkin_analysis_coverage_gate.py` script (issue #1464's slice 2). Every
assertion here is a structural sensor over shipped SKILL.md prose, not a
bare import/smoke test.
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, grep, section

SKILL = PLUGIN_ROOT / "skills" / "cd-test-architecture" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text(encoding="utf-8")


def _step_6_section() -> str:
    return section(_text(), r"^### 6\. Report", boundary_pattern=r"^## Output")


def test_cd_test_architecture_skill_md_exists():
    assert SKILL.is_file()


def test_step_6_invokes_the_gate_script_by_name_with_cd_test_architecture_config():
    section_text = _step_6_section()
    assert "gherkin_analysis_coverage_gate.py" in section_text
    assert grep(r"--config\s+cd-test-architecture", section_text)


def test_step_6_reports_the_three_way_exit_contract():
    section_text = _step_6_section()
    assert grep(r"\bOK\b", section_text)
    assert grep(r"missing", section_text, ignore_case=True)
    assert grep(r"gate did not run", section_text, ignore_case=True)


def test_exhaustive_surface_type_discovery_mandatory_default_string_present_verbatim():
    assert (
        "Exhaustive surface-type discovery is the mandatory default" in _text()
    )


def test_none_found_row_inclusion_rule_is_stated():
    text = _text()
    assert grep(r"`None found`", text)
    assert grep(r"rather than (omitting|an omitted)", text, ignore_case=True)
