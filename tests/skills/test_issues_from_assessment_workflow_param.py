"""Contract: /issues-from-assessment accepts --workflow <name> and templates
BOTH filesystem paths AND tracker-label strings so a workflow run doesn't
leak another workflow's name into operator-visible tags on
GitHub/GitLab/ADO/Jira.

Plan: plans/test-improve-orchestrator.md — Slice 11 (Step 11.1 + 11.4).

Note (issue #674 port): the bats original asserted a --workflow default of
`test-modernize`, retired by #566's consolidation of /test-modernize +
/test-upgrade into /test-improve. The assertion below tracks the current
shipped default (`test-improve`) — same invariant, current name.

Ported from tests/skills/issues_from_assessment_workflow_param_tests.bats
(issue #674).
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, grep, section

SKILL = PLUGIN_ROOT / "skills" / "issues-from-assessment" / "SKILL.md"
COV_BASELINE = PLUGIN_ROOT / "skills" / "coverage-baseline" / "SKILL.md"
COV_DELTA = PLUGIN_ROOT / "skills" / "coverage-delta" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text()


def _parse_arguments_section() -> str:
    return section(
        _text(),
        r"^## Parse Arguments",
        boundary_pattern=r"^## ",
        include_start_line=False,
    )


# --- Step 11.1: --workflow surface -------------------------------------------


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


# --- Step 11.1: filesystem paths templated on <workflow> ---------------------


def test_skill_memory_paths_use_workflow_template():
    assert grep(r"\.claude/memory/<workflow>/", _text())


def test_skill_plan_paths_use_workflow_template():
    assert grep(r"\.claude/plans/<workflow>/", _text())


# --- Step 11.1: tracker-label strings templated on <workflow> ----------------
# The Design Critic finding: operator-visible labels must not leak a
# hardcoded workflow name. Every literal workflow name inside --label /
# System.Tags= / labels[] must be replaced with <workflow>.


def test_skill_label_strings_use_workflow_template_no_literal_test_modernize():
    # Look for --label lines and reject any that hard-code test-modernize.
    lines = [ln for ln in _text().splitlines() if grep(r"--label", ln)]
    assert lines
    assert not any(grep(r"--label[^\n]*test-modernize", ln) for ln in lines)


def test_skill_system_tags_strings_use_workflow_template_no_literal_test_modernize():
    lines = [ln for ln in _text().splitlines() if grep(r"System\.Tags=", ln)]
    assert lines
    assert not any(grep(r"System\.Tags=[^\n]*test-modernize", ln) for ln in lines)


def test_skill_label_snippet_references_workflow():
    assert grep(r"--label[^\n]*<workflow>", _text())


def test_skill_system_tags_snippet_references_workflow():
    assert grep(r"System\.Tags=[^\n]*<workflow>", _text())


# --- Step 11.1: test-improve example ------------------------------------------


def test_skill_names_test_improve_as_a_supported_workflow_value():
    assert "test-improve" in _text()


# --- Step 11.4: coverage-baseline + coverage-delta name test-improve ---------


def test_coverage_baseline_skill_md_references_test_improve_as_a_supported_workflow():
    assert "test-improve" in COV_BASELINE.read_text()


def test_coverage_delta_skill_md_references_test_improve_as_a_supported_workflow():
    assert "test-improve" in COV_DELTA.read_text()
