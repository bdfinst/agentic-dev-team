"""Content-guard tests for cd-test-architecture/SKILL.md's `## Output` →
`### Companion: test-double setup guide` subsection (issue #1436, sub-issue
of epic #1431, depends on #1433/#1434/#1435). Traces to the (transient) plan
file plans/issue-1436-cd-test-architecture-test-double-setup-guide.md — cite
the issue number alongside the plan path since the plan file is
gitignored/transient (deleted after implementation, per this repo's
CLAUDE.md) and issue #1436 is the durable reference once it's gone.

This file covers Step 1.1 (the whole slice): the setup guide's trigger
condition (independent of Step 4b's Build/Document-only outcome), its output
path and chat-only-append behavior, the per-component section shape (tool +
purpose, doc link, configuration steps, example prompt, closing
`/apply-test-doubles <path>` command), the three per-component
classification cases (testcontainers / virtual-service-library /
hand-rolled fallback), the Downstream-service no-posed-sub-question fallback
default, and the "no off-gate components → no file" rule.

Every assertion below is scoped to the new `### Companion: test-double
setup guide` subsection (via the shared
`cd_test_architecture_setup_guide_section` helper) rather than an unscoped
whole-file substring check, per this session's established
false-positive-avoidance discipline (#1433 round 1/2 findings) and the
plan's explicit AC (every new content-guard assertion scoped to the specific
new subsection).
"""

from __future__ import annotations

from skill_doc_helpers import (
    PLUGIN_ROOT,
    cd_test_architecture_setup_guide_section,
    collapsed,
    grep,
)

SKILL = PLUGIN_ROOT / "skills" / "cd-test-architecture" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text(encoding="utf-8")


def _section() -> str:
    return collapsed(cd_test_architecture_setup_guide_section(_text()))


# --- Subsection presence and placement --------------------------------------


def test_subsection_exists_under_output_before_integration():
    text = _text()
    output_idx = text.index("## Output")
    subsection_idx = text.index("### Companion: test-double setup guide")
    integration_idx = text.index("## Integration")
    assert output_idx < subsection_idx < integration_idx
    assert cd_test_architecture_setup_guide_section(text).strip() != ""


# --- Trigger is independent of the Step 4b Build/Document-only decision ----


def test_setup_guide_trigger_is_independent_of_build_document_decision():
    sec = _section()
    assert grep(
        r"independent of that component's Step 4b Build/Document-only "
        r"outcome",
        sec,
        ignore_case=True,
    )
    assert grep(
        r"even when the operator chose Document-only for that component",
        sec,
        ignore_case=True,
    )
    assert grep(r"the run was non-interactive", sec, ignore_case=True)
    assert grep(
        r"exactly as it would if the operator had chosen to build it",
        sec,
        ignore_case=True,
    )


# --- Per-component section shape --------------------------------------------


def test_testcontainers_section_has_all_four_elements_and_apply_command():
    sec = _section()
    assert grep(r"Tool name \+ one-line purpose", sec)
    assert grep(r"Doc link", sec)
    assert grep(r"Configuration steps", sec)
    assert grep(r"One concrete, ready-to-run example prompt", sec)
    assert grep(r"/apply-test-doubles <path>", sec)
    assert grep(
        r"\*\*Testcontainers\*\*.*name the testcontainers tool",
        sec,
        ignore_case=True,
    )


def test_library_default_section_names_catalog_or_existing_tool():
    sec = _section()
    assert grep(
        r"name the existing-tool-detected or catalog default tool per "
        r"`?virtual-service-libraries\.md`?'s Resolution order",
        sec,
        ignore_case=True,
    )


def test_library_named_override_section_names_operator_choice_not_default():
    sec = _section()
    assert grep(
        r"the operator's chosen library, not the catalog default, when a "
        r"named override was given",
        sec,
        ignore_case=True,
    )


def test_hand_rolled_fallback_section_omits_doc_link_keeps_other_elements():
    sec = _section()
    # Positive assertion the other three elements are present, paired with
    # the doc-link-omission negative below — per this session's
    # unsupported-negative-assertion discipline.
    assert grep(
        r"no doc link; the other three elements \(name\+purpose, "
        r"configuration steps, and the example prompt\) still describe the "
        r"specific fake/contract-test to write for that component",
        sec,
        ignore_case=True,
    )
    hand_rolled_bullet = sec[sec.index("**Hand-rolled fallback**"):]
    assert not grep(r"doc link to", hand_rolled_bullet, ignore_case=True)


def test_document_only_downstream_component_still_gets_resolved_library_classification():
    # The design-critic-flagged fallback-default case: a Document-only /
    # non-interactive / ambiguous-top-level Downstream-service component
    # still gets the ambiguous-sub-answer-rule default, not an omission.
    sec = _section()
    assert grep(
        r"the operator chose Document-only, the run was non-interactive, "
        r"or the top-level answer was ambiguous",
        sec,
        ignore_case=True,
    )
    assert grep(
        r"the same Resolution-order default the ambiguous-sub-answer rule "
        r"already defines",
        sec,
        ignore_case=True,
    )
    assert grep(
        r"never a guess at what the operator would have answered, and "
        r"never an omitted section",
        sec,
        ignore_case=True,
    )


def test_two_components_sharing_a_tool_each_get_their_own_section():
    sec = _section()
    assert grep(
        r"even when two components resolve to the same tool, each still "
        r"gets its own section with its own component-specific example "
        r"prompt",
        sec,
        ignore_case=True,
    )


def test_non_off_gate_component_gets_no_section():
    sec = _section()
    assert grep(
        r"A non-off-gate component \(no adapter-double recommendation at "
        r"all\) gets no section",
        sec,
        ignore_case=True,
    )


def test_no_stack_profile_states_that_plainly_not_an_invented_citation():
    sec = _section()
    assert grep(
        r'state that plainly \(e\.g\. "No matching stack profile for this '
        r'component"\) rather than citing a profile that was never resolved',
        sec,
        ignore_case=True,
    )


def test_every_section_ends_with_apply_test_doubles_command_using_report_path():
    # Asserts <path> is the main report's own resolved path, not the setup
    # guide's own path — the round-1-review-fixed ambiguity.
    sec = _section()
    assert grep(r"/apply-test-doubles <path>", sec)
    assert grep(
        r"always the \*\*main assessment report's own resolved path\*\*",
        sec,
        ignore_case=True,
    )
    assert grep(r"\.dev-team-reports/cd-test-architecture-<app>\.md", sec)
    assert grep(r"never the setup guide's own path", sec, ignore_case=True)
    assert grep(r"per #1437's own issue text", sec, ignore_case=True)
    assert grep(r"/apply-test-doubles\s*<report-path>", sec, ignore_case=True)


def test_no_off_gate_components_means_no_setup_guide_written():
    # Positive companion: assert the section states this explicitly, not
    # just an absence check on the section text.
    sec = _section()
    assert grep(
        r"When no component in the run falls into this off-gate "
        r"adapter-double decision space, write no setup-guide file or chat "
        r"section at all",
        sec,
        ignore_case=True,
    )
    assert grep(r"never an empty one", sec, ignore_case=True)


def test_setup_guide_chat_only_case_appends_to_chat_not_a_second_file():
    sec = _section()
    assert grep(
        r"In the single-component chat-only case \(the main report goes to "
        r"chat, not a file\), the setup guide's content is appended to "
        r"that same chat output instead of written as a second file",
        sec,
        ignore_case=True,
    )


def test_setup_guide_path_matches_dev_team_reports_convention_no_legacy_path():
    sec = _section()
    # Positive assertion for `.dev-team-reports/`, negative assertion the
    # legacy `reports/` path is never named — scoped to this subsection.
    assert grep(r"\.dev-team-reports/<app>-test-double-setup\.md", sec)
    assert not grep(r"(?<!\.dev-team-)reports/<app>-test-double-setup", sec)


def test_config_steps_cite_stack_profile_not_restate_it():
    sec = _section()
    assert grep(
        r"Configuration steps.*that cite\s*—\s*never restate\s*—\s*the "
        r"same `?test-stack-profiles/<stack>\.md`? entry",
        sec,
        ignore_case=True,
    )
    assert grep(r"virtual-service-libraries\.md`? entry", sec, ignore_case=True)
