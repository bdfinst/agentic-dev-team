"""#811 — the two skeletons the language issues (#807 Python, #808 JS/TS,
#809 C#, #810 Java) plug into: the "Build-time lanes" registry section in
static-analysis-integration's tool-configs.md and the per-language setup
guide language-setup.md. Each carries one section per language so the four
language branches land into disjoint regions. A language whose lane has not
yet landed keeps its placeholder ("No lane registered") and is skipped by
the mechanism; the C# lane (test_static_analysis_csharp_lane.py) and Java
lane (test_static_analysis_java_lane.py) are registered.
"""

from __future__ import annotations

import re

from skill_doc_helpers import PLUGIN_ROOT, grep, section_outside_code

REFERENCES = PLUGIN_ROOT / "skills" / "static-analysis-integration" / "references"
TOOL_CONFIGS = REFERENCES / "tool-configs.md"
LANGUAGE_SETUP = REFERENCES / "language-setup.md"
SAI_SKILL = PLUGIN_ROOT / "skills" / "static-analysis-integration" / "SKILL.md"

LANE_LANGUAGES = ("Python", "JS/TS", "C#", "Java")

# Lanes whose owning issue has not yet landed on this branch — still
# placeholders. C# (#809) and Java (#810) are registered; their
# registered-row guards live in their own test modules.
PLACEHOLDER_LANGUAGES = ("Python", "JS/TS")
PLACEHOLDER_ISSUES = ("#807", "#808")


def _registry_section() -> str:
    return section_outside_code(
        TOOL_CONFIGS.read_text(),
        r"^## Build-time lanes",
        boundary_pattern=r"^## ",
        include_start_line=True,
    )


def _guide_text() -> str:
    return LANGUAGE_SETUP.read_text()


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


# --- Build-time lanes registry skeleton (tool-configs.md)


def test_tool_configs_has_a_build_time_lanes_registry_section():
    assert grep(r"^## Build-time lanes", TOOL_CONFIGS.read_text())


def test_registry_documents_the_capability_slot_row_shape():
    s = _flat(_registry_section())
    for element in (
        "autofix",
        "diagnostic",
        "ordered provider list",
        "detection probe",
        "extensions",
    ):
        assert element in s, f"registry row shape missing: {element}"


def test_registry_defers_mechanism_and_contract_to_the_build_reference():
    """Scoping, the fix loop, binding, and the qualification contract are
    specified once, in the build skill's mechanism reference — the registry
    points there instead of restating them."""
    assert "static-self-heal.md" in _registry_section()


def test_registry_has_one_subsection_per_language():
    s = _registry_section()
    for lang in LANE_LANGUAGES:
        assert grep(rf"^### {re.escape(lang)} lane", s), f"missing lane subsection: {lang}"


def test_each_registry_placeholder_names_its_owning_language_issue():
    s = _registry_section()
    for issue in PLACEHOLDER_ISSUES:
        assert issue in s, f"registry placeholder missing owning issue: {issue}"


def test_unregistered_lanes_remain_placeholders():
    """A lane subsection whose language issue has not landed stays a
    placeholder — the self-heal pass skips it with one info line."""
    s = _registry_section()
    for lang in PLACEHOLDER_LANGUAGES:
        lane = section_outside_code(
            s,
            rf"^### {re.escape(lang)} lane",
            boundary_pattern=r"^### ",
            include_start_line=False,
        )
        assert "No lane registered" in lane, f"{lang} lane is not a placeholder"


# --- per-language setup guide skeleton (language-setup.md)


def test_language_setup_guide_exists():
    assert LANGUAGE_SETUP.is_file()


def test_guide_documents_the_opt_out_toggle():
    assert "DEV_TEAM_STATIC_SELF_HEAL=off" in _guide_text()


def test_guide_states_the_per_lane_section_contract():
    s = _flat(_guide_text()).lower()
    for element in (
        "autofix-capable",
        "diagnostic-only",
        "repo-level",
        "config files",
        "probe",
        "recognized equivalent providers",
    ):
        assert element in s, f"section contract missing: {element}"


def test_guide_points_to_project_init_as_the_one_command_install_path():
    assert "/project-init" in _guide_text()


def test_guide_has_one_section_per_language():
    text = _guide_text()
    for lang in LANE_LANGUAGES:
        assert grep(rf"^## {re.escape(lang)}$", text), f"missing guide section: {lang}"


def test_each_guide_placeholder_names_its_owning_language_issue():
    text = _guide_text()
    for issue in PLACEHOLDER_ISSUES:
        assert issue in text, f"guide placeholder missing owning issue: {issue}"


# --- discoverability


def test_skill_related_section_lists_the_language_setup_guide():
    assert "references/language-setup.md" in SAI_SKILL.read_text()
