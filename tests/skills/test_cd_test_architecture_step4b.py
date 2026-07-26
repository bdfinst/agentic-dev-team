"""Step 4b (build-vs-document decision) content-guard tests for
`cd-test-architecture/SKILL.md` — Step 1.1 of
plans/issue-1433-cd-test-architecture-step-4b.md.

Every assertion below is scoped to the new `### 4b.` section (or, for the
Role/Constraints/Integration acknowledgment tests, to the specific existing
section each amendment landed in) rather than an unscoped whole-file
substring check, per the plan's Design & Architecture Critic round-1/2
findings (false-positive risk against unrelated pre-existing text).

Backtick note: the plan's Acceptance Criteria (AC10) and Step 1.1 IMPLEMENT
text both specify the Role/Constraints/Integration appended text with
backticks around `/build` (e.g. "invoking `/build` itself"); the Step 1.1
TEST bullet's inline verbatim quotes drop those backticks (likely a nested-
backtick markdown-rendering artifact in the plan file itself — code spans
can't easily contain further backticks). The three acknowledgment tests
below match the core wording from both sources with the backticks around
`/build` treated as optional, so the assertion holds against the actual
shipped text (which carries them, per AC10) without being a redesign of the
plan's stated check.
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, collapsed, grep, section

SKILL = PLUGIN_ROOT / "skills" / "cd-test-architecture" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text(encoding="utf-8")


def _step_4b_section() -> str:
    return section(_text(), r"^### 4b\.", boundary_pattern=r"^### 5\.")


def _role_paragraph() -> str:
    """The `Role:` paragraph is hard-wrapped across several lines in the
    file — capture from the `Role:`-starting line through the next blank
    line, then collapse whitespace so a phrase split mid-sentence across
    lines still matches a single-line regex."""
    lines = _text().splitlines()
    out: list[str] = []
    capturing = False
    for line in lines:
        if line.startswith("Role:"):
            capturing = True
        if capturing:
            if line.strip() == "" and out:
                break
            out.append(line)
    return collapsed("\n".join(out))


def _constraints_section() -> str:
    return section(_text(), r"^## Constraints", boundary_pattern=r"^## ")


def _integration_section() -> str:
    return section(_text(), r"^## Integration", boundary_pattern=r"^## ")


# --- Step 4b section presence and placement --------------------------------


def test_step_4b_section_exists_between_step_4_and_5():
    text = _text()
    step4_idx = text.index("### 4. Recommend the target architecture")
    step4b_idx = text.index("### 4b. Build-vs-document decision")
    step5_idx = text.index("### 5. Produce a migration path")
    assert step4_idx < step4b_idx < step5_idx
    assert _step_4b_section().strip() != ""


def test_step_4b_asks_once_batched_per_run_not_per_adapter_kind():
    sec = _step_4b_section()
    assert grep(r"\bonce\b", sec, ignore_case=True)
    assert grep(r"batch(ed)?", sec, ignore_case=True)


def test_step_4b_documents_unattended_default_cites_human_oversight_protocol():
    sec = _step_4b_section()
    assert grep(
        r"--yes|DEV_TEAM_AUTO_APPROVE=1|no-TTY|no TTY|human-oversight-protocol",
        sec,
        ignore_case=True,
    )
    assert grep(r"document-only|document only", sec, ignore_case=True)
    assert grep(r"no prompt", sec, ignore_case=True)


def test_step_4b_ambiguous_answer_defaults_to_document_only():
    sec = _step_4b_section()
    assert grep(r"maybe", sec, ignore_case=True)
    assert grep(r"not sure", sec, ignore_case=True)
    assert grep(r"\byes\b", sec, ignore_case=True)
    assert grep(r"\bno\b", sec, ignore_case=True)
    assert grep(r"silence|empty|no answer", sec, ignore_case=True)
    assert grep(r"document-only|document only", sec, ignore_case=True)


def test_step_4b_no_gap_no_behavior_change():
    sec = _step_4b_section()
    assert grep(r"no prompt", sec, ignore_case=True)
    assert grep(r"unchanged", sec, ignore_case=True)


def test_step_4b_proposes_story_language_not_dispatch():
    sec = _step_4b_section()
    assert grep(r"propose", sec, ignore_case=True)
    assert not grep(r"dispatch a Story", sec, ignore_case=True)
    assert not grep(r"invoke /build", sec, ignore_case=True)


# --- Role / Constraints / Integration acknowledgment ------------------------


def test_role_line_acknowledges_step_4b_branch():
    para = _role_paragraph()
    assert grep(
        r"Step 4b's build-vs-document ask is this skill's one interactive "
        r"branch point, and even there it proposes a Story rather than "
        r"invoking `?/build`? itself\.",
        para,
    )


def test_constraints_section_acknowledges_step_4b_branch():
    sec = collapsed(_constraints_section())
    assert grep(
        r"including Step 4b's build-vs-document ask: it proposes a "
        r"downstream Story, it never invokes `?/build`? or edits code "
        r"directly\.",
        sec,
    )


def test_integration_section_acknowledges_step_4b_branch():
    sec = collapsed(_integration_section())
    assert grep(
        r"except that Step 4b may propose a downstream Story as part of "
        r"that hand-off — it still never invokes `?/build`? itself\.",
        sec,
    )


# --- Database-specific branch (Step 1.2) ------------------------------------

FAKE_CAVEAT = (
    "Caveat: this hand-rolled Fake cannot verify actual SQL, mapping, or "
    "schema correctness the way a real-engine test can — a deliberate "
    "coverage trade-off, not a silent downgrade."
)


def test_database_branch_dispatches_testcontainers_story_when_accepted():
    sec = collapsed(_step_4b_section())
    assert grep(r"testcontainers", sec, ignore_case=True)
    assert grep(r"propose", sec, ignore_case=True)
    assert grep(r"Database Sandbox", sec)
    assert grep(r"Transaction Rollback", sec)
    assert grep(r"Table Truncation", sec)


def test_database_branch_declined_proposes_fake_not_document_only():
    sec = _step_4b_section()
    decline_bullet = section(
        sec,
        r"\*\*Testcontainers declined\*\*",
        boundary_pattern=r"^- \*\*Ambiguous",
    )
    assert grep(r"\bFake\b", decline_bullet)
    assert grep(r"in-memory repository", decline_bullet, ignore_case=True)
    assert not grep(r"document-only|document only", decline_bullet, ignore_case=True)


def test_hand_rolled_fake_caveat_is_logged_explicitly():
    sec = _step_4b_section()
    assert FAKE_CAVEAT in sec


def test_story_titles_follow_the_bracketed_component_template():
    sec = _step_4b_section()
    assert grep(
        r"\[<component>\]\s*Add testcontainers-based real-DB test", sec
    )
    assert grep(
        r"\[<component>\]\s*Add hand-rolled Fake database double", sec
    )


def test_database_branch_cites_test_doubles_and_database_test_patterns():
    sec = _step_4b_section()
    assert grep(r"test-doubles\.md", sec)
    assert grep(r"database-test-patterns\.md", sec)


def test_ambiguous_testcontainers_answer_treated_as_decline_not_document_only():
    ambiguous_bullet = section(
        _step_4b_section(),
        r"\*\*Ambiguous or absent answer to this per-component question\*\*",
        boundary_pattern=r"^### 5\.",
    )
    ambiguous_bullet = collapsed(ambiguous_bullet)
    assert grep(r"\bdecline\b", ambiguous_bullet, ignore_case=True)
    assert grep(r"\bFake\b", ambiguous_bullet)
    assert grep(
        r"distinct from.*top-level.*document-only", ambiguous_bullet
    )
    assert grep(
        r"same ambiguous definition", ambiguous_bullet, ignore_case=True
    )


def test_knowledge_references_list_includes_test_doubles():
    text = _text()
    refs_section = section(text, r"^Grounded in these knowledge references", boundary_pattern=r"^## ")
    assert grep(r"test-doubles\.md", refs_section)


# --- Output report template (Step 1.3) --------------------------------------


def _output_section() -> str:
    return section(_text(), r"^## Output", boundary_pattern=r"^## Integration")


def test_output_template_shows_build_document_status_column():
    sec = _output_section()
    assert grep(r"Build/Document status", sec)
    assert grep(r"Build \(testcontainers\)", sec)
    assert grep(r"Build \(Fake\)", sec)
    assert grep(r"Document-only", sec)


def test_output_template_caveat_appears_conditionally_on_fake_branch():
    sec = _output_section()
    fake_row_clause = section(
        sec,
        r"row whose status is `Build \(Fake\)`",
        boundary_pattern=r"^### ",
    )
    assert FAKE_CAVEAT in fake_row_clause


def test_caveat_appears_in_both_story_and_report():
    # Same reusable FAKE_CAVEAT constant checked in both locations, so the
    # two can't drift apart into independently-typed strings — the Story
    # description (Step 1.2, database branch) and the report's output
    # template (Step 1.3, Target architecture table).
    assert FAKE_CAVEAT in _step_4b_section()
    assert FAKE_CAVEAT in _output_section()


def test_output_template_does_not_hardcode_legacy_reports_path():
    text = _text()
    assert not grep(r"(?<!\.dev-team-)reports/cd-test-architecture-", text)
