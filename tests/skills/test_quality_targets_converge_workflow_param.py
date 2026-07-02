"""Contract: /quality-targets-converge accepts --workflow <name> and
templates memory + plan paths on it. The [Phase-2 amendment] gherkin-
bindings escape hatch is removed from BOTH the SKILL body AND
docs/agent-architecture.md so operators only see one route (the standard
Phase-2 sign-off).

Plan: plans/test-improve-orchestrator.md — Slice 11 (Step 11.2).

Ported from tests/skills/quality_targets_converge_workflow_param_tests.bats
(issue #674).
"""

from __future__ import annotations

from conftest import PLUGIN_ROOT, grep, section

SKILL = PLUGIN_ROOT / "skills" / "quality-targets-converge" / "SKILL.md"
ARCH = PLUGIN_ROOT / "docs" / "agent-architecture.md"


def _text() -> str:
    return SKILL.read_text()


def _parse_arguments_section() -> str:
    return section(
        _text(),
        r"^## Parse Arguments",
        boundary_pattern=r"^## ",
        include_start_line=False,
    )


# --- --workflow surface -------------------------------------------------------


def test_skill_parse_arguments_documents_workflow_name():
    assert "--workflow" in _parse_arguments_section()


def test_skill_parse_arguments_documents_the_workflow_default_value():
    assert grep(
        r"default.*test-improve|Defaults to.*test-improve",
        _parse_arguments_section(),
        ignore_case=True,
    )


def test_argument_hint_frontmatter_names_workflow():
    assert grep(r"^argument-hint:.*--workflow", _text())


# --- paths templated on <workflow> --------------------------------------------


def test_skill_memory_paths_use_workflow_template_no_literal_memory_test_modernize():
    assert not grep(r"memory/test-modernize/", _text())


def test_skill_plan_paths_use_workflow_template_no_literal_plans_test_modernize():
    assert not grep(r"\./plans/test-modernize/", _text())


def test_skill_memory_paths_reference_memory_workflow():
    assert grep(r"memory/<workflow>/", _text())


def test_skill_plan_paths_reference_plans_workflow_phase_5():
    assert grep(r"\./plans/<workflow>/phase-5/", _text())


# --- test-improve example -----------------------------------------------------


def test_skill_names_test_improve_as_a_supported_workflow_value():
    assert "test-improve" in _text()


# --- [Phase-2 amendment] escape hatch removed from BOTH locations -------------


def test_skill_phase_2_amendment_escape_hatch_is_absent():
    assert not grep(r"\[Phase-2 amendment\]", _text())


def test_agent_architecture_md_phase_2_amendment_paragraph_is_absent():
    assert not grep(r"\[Phase-2 amendment\]", ARCH.read_text())
