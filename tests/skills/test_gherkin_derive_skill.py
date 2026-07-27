"""Contract for the /gherkin-derive skill (epic #443, issue #441).
Standalone Gherkin derivation from code — no prior legacy-modernization
analysis required.

Note (issue #674 port): two bats assertions tracked a pre-#566
vocabulary — "does not require a /test-modernize phase-1 map" and a
hardcoded `memory/test-upgrade/` output path. #566 consolidated
/test-modernize + /test-upgrade into /test-improve and the skill's memory
path is now templated on `<workflow>`; the assertions below track the
current shipped prose (standalone / no prior `/cd-test-architecture`
analysis; `memory/<workflow>/.../gherkin.md`) — same invariant, current
names.

Ported from tests/skills/gherkin_derive_skill_tests.bats (issue #674).
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, frontmatter, grep

SKILL = PLUGIN_ROOT / "skills" / "gherkin-derive" / "SKILL.md"
AGENT_REG = PLUGIN_ROOT / "knowledge" / "agent-registry.md"
SKILLS_REG = PLUGIN_ROOT / "knowledge" / "skills-registry.md"


def _text() -> str:
    return SKILL.read_text()


def test_gherkin_derive_skill_md_exists():
    assert SKILL.is_file()


def test_frontmatter_declares_name_user_invocable_and_allowed_tools():
    fm = frontmatter(_text())
    assert grep(r"^name: *gherkin-derive", fm)
    assert grep(r"^user-invocable: *true", fm)
    assert grep(r"^allowed-tools:", fm)


def test_runs_standalone_does_not_require_prior_legacy_modernization_analysis():
    text = _text()
    assert grep(r"standalone", text, ignore_case=True)
    assert grep(r"not\W+require", text, ignore_case=True)


def test_surface_discovery_tries_openapi_routes_tests_signatures_in_order():
    # Check the ordering inside the discovery step (the frontmatter
    # summary lists all four on one line, so scope to the step body).
    text = _text()
    idx = text.find("Discover the public surface")
    assert idx != -1
    step3_idx = text.find("## Step 3", idx)
    section_text = text[idx : step3_idx if step3_idx != -1 else None]
    lines = section_text.splitlines()
    o = next(
        (i for i, ln in enumerate(lines) if grep(r"OpenAPI", ln, ignore_case=True)),
        None,
    )
    r = next(
        (i for i, ln in enumerate(lines) if grep(r"route", ln, ignore_case=True)), None
    )
    t = next(
        (
            i
            for i, ln in enumerate(lines)
            if grep(r"test name|describe|existing test", ln, ignore_case=True)
        ),
        None,
    )
    s = next(
        (
            i
            for i, ln in enumerate(lines)
            if grep(r"signature|docstring|exported function", ln, ignore_case=True)
        ),
        None,
    )
    assert o is not None and r is not None and t is not None and s is not None
    assert o < r
    assert r < t
    assert t < s


def test_presents_the_bdd_value_rubric_when_mode_is_not_supplied():
    text = _text()
    assert "--mode" in text
    assert grep(r"bdd-value-guide\.md", text, ignore_case=True)
    assert grep(r"rubric|present.*when.*not (supplied|passed)", text, ignore_case=True)


def test_defines_all_three_binding_modes():
    text = _text()
    assert grep(r"`none`|\bnone\b", text)
    assert "xunit-with-annotations" in text
    assert "bdd-runner" in text


def test_none_mode_exits_with_a_recommendation_and_writes_no_files():
    assert grep(
        r"none.*(exit|no files|no Gherkin)|exit.*recommend", _text(), ignore_case=True
    )


def test_xunit_with_annotations_writes_feature_files_only_no_framework_install():
    text = _text()
    assert grep(r"xunit-with-annotations", text, ignore_case=True)
    assert grep(
        r"no.*(runner|framework|install)|not wire|do NOT wire", text, ignore_case=True
    )


def test_bdd_runner_generates_pending_stubs_that_compile_and_fail_not_empty():
    text = _text()
    assert grep(r"bdd-runner", text, ignore_case=True)
    assert grep(r"pending", text, ignore_case=True)
    assert grep(
        r"compile.*fail|fail.*intention|red before green|not.*empty",
        text,
        ignore_case=True,
    )


def test_labels_characterization_scenarios_as_current_behavior_in_the_feature_header():
    text = _text()
    assert grep(r"characterization", text, ignore_case=True)
    assert grep(r"current behavior", text, ignore_case=True)


def test_cross_references_bdd_frameworks_md_for_per_language_wiring():
    assert "bdd-frameworks.md" in _text()


def test_writes_the_surface_inventory_under_memory_workflow():
    assert grep(r"memory/<workflow>/.*gherkin", _text())


def test_step_2_mandates_in_depth_analysis_of_named_categories():
    # issue #1450: comprehensive codebase-wide analysis must be the
    # unconditional default, not an operator-supplied instruction.
    text = _text()
    idx = text.find("Discover the public surface")
    assert idx != -1
    step3_idx = text.find("## Step 3", idx)
    section_text = text[idx : step3_idx if step3_idx != -1 else None]
    for category in (
        "controllers",
        "handlers",
        "services",
        r"domain\s+logic",
        "workflows",
        r"validation\s+rules",
        r"error\s+handling",
        r"business\s+processes",
    ):
        assert grep(category, section_text, ignore_case=True), category
    assert grep(r"mandatory|unconditional", section_text, ignore_case=True)
    assert grep(r"always on|never.*(operator|gated)", section_text, ignore_case=True)


def test_step_5_requires_analysis_coverage_section_in_inventory():
    text = _text()
    idx = text.find("## Step 5")
    assert idx != -1
    step6_idx = text.find("## Step 6", idx)
    section_text = text[idx : step6_idx if step6_idx != -1 else None]
    assert grep(r"Analysis Coverage", section_text)
    for category in (
        "controllers",
        "handlers",
        "services",
        r"domain\s+logic",
        "workflows",
        r"validation\s+rules",
        r"error\s+handling",
        r"business\s+processes",
    ):
        assert grep(category, section_text, ignore_case=True), category


def test_step_6_reports_analysis_coverage_gate_outcomes():
    text = _text()
    idx = text.find("## Step 6")
    assert idx != -1
    next_heading_idx = text.find("## Key differences", idx)
    section_text = text[idx : next_heading_idx if next_heading_idx != -1 else None]
    assert "gherkin_analysis_coverage_gate.py" in section_text
    assert grep(r"\bOK\b", section_text)
    assert grep(r"missing", section_text, ignore_case=True)
    assert grep(r"gate did not run", section_text, ignore_case=True)


def test_registered_in_skills_registry():
    assert "skills/gherkin-derive/SKILL.md" in SKILLS_REG.read_text()
    assert "skills/gherkin-derive/SKILL.md" in AGENT_REG.read_text()
