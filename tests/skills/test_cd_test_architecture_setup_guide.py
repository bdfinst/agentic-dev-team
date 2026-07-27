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
    section,
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


def test_library_section_points_to_step_4b_tool_resolution_not_restating_it():
    # arch-review finding (round 2): the Classification block previously
    # re-derived Step 4b's answer grammar (existing-tool-detected/catalog
    # default/named override) inline, creating a second source of truth
    # that could drift silently if Step 4b's grammar changed. It must now
    # name which Step 4b branch resolves the tool, not restate the rule.
    sec = _section()
    assert grep(
        r"name whichever tool Step 4b's Downstream-service branch's "
        r"construction-method sub-question resolved for this component",
        sec,
        ignore_case=True,
    )
    assert grep(
        r"see that branch above\s*—\s*not restated here",
        sec,
        ignore_case=True,
    )


def test_library_section_no_longer_restates_step_4b_answer_grammar():
    # Negative companion to the pointer assertion above: the specific
    # restated phrases from round 1 must not reappear in this bullet, or
    # the duplication the finding flagged has crept back in.
    sec = _section()
    assert not grep(
        r"name the existing-tool-detected or catalog default tool per",
        sec,
        ignore_case=True,
    )
    assert not grep(
        r"the operator's chosen library, not the catalog default, when a "
        r"named override was given",
        sec,
        ignore_case=True,
    )


def test_library_section_carries_recorded_artifact_scrub_caveat():
    # security-review finding: the setup guide is the setup-time artifact
    # where #1435's scrub-before-commit temporal ordering can actually be
    # enforced, so the virtual-service-library classification case must
    # cite that section — not just the per-tool catalog entry — and name
    # the credential-filtering hook as ordered before the first recording.
    sec = _section()
    assert grep(
        r"virtual-service-libraries\.md.{0,3}s .Recorded artifacts contain "
        r"real traffic . scrub before commit. section",
        sec,
        ignore_case=True,
    )
    assert grep(
        r"in addition to the per-tool catalog entry",
        sec,
        ignore_case=True,
    )
    assert grep(
        r"credential-filtering hook as a step ordered before the first "
        r"recording",
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
    # Bounded to the Hand-rolled fallback bullet itself — not a slice to the
    # end of the whole subsection, which would drag the later
    # Downstream-service-no-posed-sub-question paragraph (and its own
    # "Resolution order" prose) into this negative assertion's fixture
    # (test-smell-review finding).
    hand_rolled_bullet = collapsed(
        section(
            cd_test_architecture_setup_guide_section(_text()),
            r"\*\*Hand-rolled fallback\*\*",
            boundary_pattern=(
                r"\*\*Downstream-service components with no posed "
                r"sub-question\.\*\*"
            ),
        )
    )
    assert not grep(r"doc link to", hand_rolled_bullet, ignore_case=True)
    # arch-review finding (round 2): the parenthetical previously restated
    # Step 4b's "no protocol-appropriate library" rule body inline; it must
    # now point at that branch instead.
    assert grep(
        r"Step 4b's Downstream-service branch's no-matching-library "
        r"fallback applying to this component's adapter kind",
        hand_rolled_bullet,
        ignore_case=True,
    )
    assert grep(
        r"see that branch above, not restated here", hand_rolled_bullet, ignore_case=True
    )
    assert not grep(
        r"no protocol-appropriate library exists for the component's "
        r"adapter kind",
        hand_rolled_bullet,
        ignore_case=True,
    )


def test_document_only_downstream_component_still_gets_resolved_library_classification():
    # The design-critic-flagged fallback-default case: a Document-only /
    # non-interactive / ambiguous-top-level Downstream-service component
    # still gets Step 4b's tool-resolution rule applied fresh to a row that
    # never got a sub-question at all — this is NOT a restatement of Step
    # 4b's own ambiguous-sub-answer rule, which is scoped only to
    # `Build (Fake)` rows where the sub-question WAS posed. Per the
    # arch-review round-2 finding, this paragraph now points at Step 4b's
    # own text for the actual resolution mechanics rather than re-deriving
    # them (the round-1 ai-provenance-review fix addressed the false
    # restatement claim; this fixes the still-duplicated rule body).
    sec = _section()
    assert grep(
        r"the operator chose Document-only, the run was non-interactive, "
        r"or the top-level answer was ambiguous",
        sec,
        ignore_case=True,
    )
    assert grep(
        r"the same tool-resolution rule Step 4b's sub-question applies when "
        r"it does fire",
        sec,
        ignore_case=True,
    )
    assert grep(
        r"see the Downstream-service branch above for what determines the "
        r"tool, not restated here",
        sec,
        ignore_case=True,
    )
    assert grep(
        r"applied to rows that never got a sub-question in the first "
        r"place, because this guide's trigger is independent of the "
        r"Build/Document-only outcome, never a guess and never omitted",
        sec,
        ignore_case=True,
    )
    assert not grep(
        r"the same Resolution order \(existing-tool-detected . catalog "
        r"default\) that `?virtual-service-libraries\.md`? defines",
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
    # guide's own path — the round-1-review-fixed ambiguity. Now that #1437
    # has shipped, this grounds itself in the real skill's own contract
    # rather than a quoted issue-text excerpt (arch-review, #1437's
    # code-review panel: the issue-text quote had already drifted from the
    # shipped skill's actual, optional-positional argument shape).
    sec = _section()
    assert grep(r"/apply-test-doubles <path>", sec)
    assert grep(
        r"always the \*\*main assessment report's own resolved path\*\*",
        sec,
        ignore_case=True,
    )
    assert grep(r"\.dev-team-reports/cd-test-architecture-<app>\.md", sec)
    assert grep(r"never the setup guide's own path", sec, ignore_case=True)
    assert grep(
        r"per `\.\./apply-test-doubles/SKILL\.md`'s own Parse Arguments "
        r"section, not restated here",
        sec,
        ignore_case=True,
    )
    assert not grep(r"per #1437's own issue text", sec, ignore_case=True)


def test_chat_only_case_apply_test_doubles_has_no_path_to_substitute():
    # arch-review finding (round 2): "always" contradicted the subsection's
    # own single-component chat-only case, where the main report goes to
    # chat rather than a file, so there is no main-report path to
    # substitute for <path>. The closing command must state that gap
    # explicitly rather than silently falling back to the setup guide's own
    # path.
    sec = _section()
    assert grep(
        r"In the single-component chat-only case, there is no saved "
        r"main-report file to substitute for `?<path>`?",
        sec,
        ignore_case=True,
    )
    assert grep(
        r"the assessment output is in this chat session, not a saved file",
        sec,
        ignore_case=True,
    )
    assert grep(
        r"the closing command is emitted with no path argument",
        sec,
        ignore_case=True,
    )
    assert grep(
        r"plain `?/apply-test-doubles`?", sec, ignore_case=True
    )


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
    # Filename matches the main report's own naming convention
    # (`cd-test-architecture-<app>.md` with `.md` replaced by
    # `-test-double-setup.md`) — not the app-first inversion the original
    # build shipped (ai-provenance-review finding).
    assert grep(
        r"\.dev-team-reports/cd-test-architecture-<app>-test-double-setup\.md",
        sec,
    )
    assert not grep(
        r"(?<!\.dev-team-)reports/cd-test-architecture-<app>-test-double-setup",
        sec,
    )


def test_config_steps_cite_stack_profile_not_restate_it():
    sec = _section()
    assert grep(
        r"Configuration steps.*that cite\s*—\s*never restate\s*—\s*the "
        r"same `?test-stack-profiles/<stack>\.md`? entry",
        sec,
        ignore_case=True,
    )
    assert grep(r"virtual-service-libraries\.md`? entry", sec, ignore_case=True)


def test_setup_guide_adopts_report_template_header_and_provenance():
    # arch-review finding (round 2): the setup guide is a second report
    # artifact written into .dev-team-reports/ alongside a main report that
    # already adopted report-template.md's header/Provenance contract, with
    # no stated rationale for the setup guide diverging. It must reference
    # the shared contract using the exact sentence the contract specifies,
    # and state what its own **Scope** field covers.
    sec = _section()
    assert grep(
        r"For the header block and closing Provenance section, follow "
        r"`?knowledge/report-template\.md`?",
        sec,
        ignore_case=True,
    )
    assert grep(
        r"the per-component sections below are this guide's own body",
        sec,
        ignore_case=True,
    )
    assert grep(
        r"\*\*Scope\*\*`?\s+reads the components covered by this guide",
        sec,
        ignore_case=True,
    )
    assert grep(
        r"not the full application inventory from Step 1",
        sec,
        ignore_case=True,
    )
