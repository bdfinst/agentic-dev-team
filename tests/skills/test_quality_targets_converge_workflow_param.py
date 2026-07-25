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

from skill_doc_helpers import PLUGIN_ROOT, grep, section

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


def _dispatch_table_row() -> str:
    """Scope to the 'Coverage gap on a single file' dispatch-table rows
    specifically (issue #968) — an unscoped whole-file grep would pass even
    if the branching text lived in the wrong place."""
    text = _text()
    lines = text.splitlines()
    out = []
    for line in lines:
        if line.startswith("|") and "Coverage gap on a single file" in line:
            out.append(line)
    return "\n".join(out)


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
    assert grep(r"\.claude/memory/<workflow>/", _text())


def test_skill_plan_paths_reference_plans_workflow_phase_7():
    assert grep(r"\.claude/plans/<workflow>/phase-7/", _text())


# --- test-improve example -----------------------------------------------------


def test_skill_names_test_improve_as_a_supported_workflow_value():
    assert "test-improve" in _text()


# --- --refactor-mode surface (issue #968) -------------------------------------


def test_argument_hint_frontmatter_names_refactor_mode():
    assert grep(r"^argument-hint:.*--refactor-mode", _text())


def test_parse_arguments_documents_refactor_mode_default_and_visibility_line():
    s = _parse_arguments_section()
    assert grep(r"--refactor-mode", s)
    assert grep(
        r"default.*refactor-allowed|refactor-allowed.*default", s, ignore_case=True
    )
    assert grep(
        r"not specified by caller|defaulting to refactor-allowed", s, ignore_case=True
    )


def test_dispatch_table_documents_no_refactor_branch_writes_backlog_not_story():
    row = _dispatch_table_row()
    assert grep(r"no-refactor", row)
    assert grep(r"refactor-backlog\.md", row)
    # The no-refactor row legitimately mentions [Refactor-for-testability] as
    # part of a negated instruction ("Do not propose a [...] Story") — assert
    # the negation is present, not that the bracket phrase is wholly absent.
    assert grep(
        r"no-refactor.*not.*propose.*\[Refactor-for-testability\]",
        row,
        ignore_case=True,
    )


def test_dispatch_table_documents_refactor_allowed_branch_unchanged():
    row = _dispatch_table_row()
    assert grep(r"refactor-allowed", row)
    assert grep(r"\[Refactor-for-testability\]", row)


# --- [Phase-2 amendment] escape hatch removed from BOTH locations -------------


def test_skill_phase_2_amendment_escape_hatch_is_absent():
    assert not grep(r"\[Phase-2 amendment\]", _text())


def test_agent_architecture_md_phase_2_amendment_paragraph_is_absent():
    assert not grep(r"\[Phase-2 amendment\]", ARCH.read_text())
