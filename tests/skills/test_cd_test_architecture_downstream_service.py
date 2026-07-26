"""Downstream-service branch content-guard tests for
`cd-test-architecture/SKILL.md`. Traces to issue #1434 (sub-issue of epic
#1431) and Steps 1.1/1.2 of the (transient) plan file
plans/issue-1434-cd-test-architecture-downstream-service-branch.md — cite
the issue number alongside the plan path since the plan file is
gitignored/transient (deleted after implementation, per this repo's
CLAUDE.md) and issue #1434 is the durable reference once it's gone.

This file covers Step 1.1 (Step 1's ownership/deployability note) and
Step 1.2 (the new `#### Downstream-service branch` subsection under Step
4b, plus the generalized shared Step 4b intro sentence). Step 1.3's Story
shapes and the Output/knowledge-reference generalizations land in a later
step of the same plan. Assertions here are scoped to the specific section
they target, mirroring the sibling `test_cd_test_architecture_step4b.py`'s
scoped-boundary discipline (a boundary regex must be empirically verified
reachable, not assumed — a prior round of that file family shipped an
unreachable boundary and it was a real bug, issue #1433 round 4).
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, collapsed, grep, section

SKILL = PLUGIN_ROOT / "skills" / "cd-test-architecture" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text(encoding="utf-8")


def _step_1_section() -> str:
    return section(_text(), r"^### 1\.", boundary_pattern=r"^### 2\.")


def _step_4b_intro_paragraph() -> str:
    """The shared, pre-existing Step 4b intro text — from the `### 4b.`
    heading up to (not including) the first `#### ` sub-heading
    (`#### Database-specific branch`). This is the general, non-branch-
    specific scaffold text #1433 shipped and this slice amends (the
    "choose exactly one of the options listed for that row" sentence) —
    distinct from either branch's own subsection."""
    return section(_text(), r"^### 4b\.", boundary_pattern=r"^#### ")


def _downstream_service_branch_section() -> str:
    """Scoped to the new `#### Downstream-service branch` subsection.
    Empirically verified boundary: this subsection is currently the last
    `####` sub-heading under Step 4b (no sibling `#### ` follows it), so
    `^### 5\\.` is the reachable boundary today — not `^#### `, which
    would never match and silently return "rest of the file" (the
    unreachable-boundary bug #1433 round 4 warns against). If a future
    slice adds another `#### ` subsection after this one, this boundary
    should be revisited the same way `_database_specific_branch_section()`
    already was in the sibling file."""
    return section(
        _text(),
        r"^#### Downstream-service branch",
        boundary_pattern=r"^### 5\.",
    )


# --- Boundary reachability sanity check -------------------------------------


def test_step_1_section_boundary_is_reachable():
    # Empirically verify the scoping boundary actually narrows the text —
    # not an assumption. Step 1's own heading and the Graph-assisted
    # inventory paragraph must be present; Step 2's heading and content
    # must be excluded.
    sec = _step_1_section()
    assert "### 1. Inventory the application's components" in sec
    assert "Graph-assisted inventory" in sec
    assert "### 2." not in sec
    assert "Inventory the existing tests and classify them" not in sec


# --- Step 1.1: ownership/deployability note ---------------------------------


def test_step_1_records_ownership_for_downstream_service_components():
    sec = _step_1_section()
    assert grep(r"API Consumer", sec)
    assert grep(r"Event Consumer", sec)
    assert grep(r"Event Producer", sec)
    assert grep(r"team-controlled", sec, ignore_case=True)
    assert grep(r"third-party", sec, ignore_case=True)


def test_step_1_cites_component_test_patterns_ownership_guidance():
    sec = _step_1_section()
    assert grep(r"component-test-patterns\.md", sec)


# --- Step 1.2: Downstream-service branch ------------------------------------


def test_downstream_service_branch_section_boundary_is_reachable():
    # Empirically verify the scoping boundary actually narrows the text —
    # not an assumption (issue #1433 round 4 lesson). The subsection's own
    # heading and content must be present; Step 5's heading and content
    # must be excluded.
    sec = _downstream_service_branch_section()
    assert "#### Downstream-service branch" in sec
    assert "Third-party/other-team" in sec
    assert "### 5." not in sec
    assert "Produce a migration path" not in sec


def test_downstream_service_branch_exists_after_database_branch():
    text = _text()
    database_idx = text.index("#### Database-specific branch")
    downstream_idx = text.index("#### Downstream-service branch")
    step5_idx = text.index("### 5. Produce a migration path")
    assert database_idx < downstream_idx < step5_idx
    assert _downstream_service_branch_section().strip() != ""


def test_downstream_service_branch_cites_component_test_patterns():
    sec = _downstream_service_branch_section()
    assert grep(r"component-test-patterns\.md", sec)


def test_downstream_service_branch_reuses_same_batched_prompt_not_a_second_one():
    sec = collapsed(_downstream_service_branch_section())
    assert grep(r"\*?same\*?\s+batched per-run prompt", sec, ignore_case=True)
    assert grep(r"not a second prompt", sec, ignore_case=True)


def test_team_controlled_row_offers_three_options():
    sec = _downstream_service_branch_section()
    team_controlled_bullet = collapsed(
        section(
            sec,
            r"\*\*Team-controlled\*\*",
            boundary_pattern=r"^(- \*\*|### )",
        )
    )
    assert grep(r"Build \(testcontainers\)", team_controlled_bullet)
    assert grep(r"Build \(Fake\)", team_controlled_bullet)
    assert grep(r"Document-only", team_controlled_bullet)


def test_third_party_row_offers_only_two_options_no_testcontainers():
    sec = _downstream_service_branch_section()
    third_party_bullet = collapsed(
        section(
            sec,
            r"\*\*Third-party/other-team\*\*",
            boundary_pattern=r"^(- \*\*|### )",
        )
    )
    assert grep(r"Build \(Fake\)", third_party_bullet)
    assert grep(r"Document-only", third_party_bullet)
    # Positive supporting text, not just an absence check (#1433's lesson:
    # an unsupported negative is the weakest kind of test).
    assert grep(
        r"Build \(testcontainers\).{0,40}is never offered",
        third_party_bullet,
        ignore_case=True,
    )


def test_not_offered_option_answer_treated_as_ambiguous():
    sec = collapsed(_downstream_service_branch_section())
    assert grep(
        r"answer naming an option not offered for a row's tier",
        sec,
        ignore_case=True,
    )
    assert grep(r"treated as ambiguous", sec, ignore_case=True)
    assert grep(r"defaulting to `?Document-only`? for that row", sec, ignore_case=True)


def test_ambiguous_answer_rule_reused_not_reinvented():
    sec = collapsed(_downstream_service_branch_section())
    assert grep(
        r"same ambiguous-answer rule as any other ambiguous answer",
        sec,
        ignore_case=True,
    )
    assert grep(r"not a new rule", sec, ignore_case=True)


def test_step_4b_intro_no_longer_overclaims_fixed_three_options():
    intro = collapsed(_step_4b_intro_paragraph())
    assert not grep(r"exactly one of three options", intro, ignore_case=True)
    assert grep(
        r"exactly one of the options listed for that row", intro, ignore_case=True
    )
    assert grep(r"up to three", intro, ignore_case=True)
    assert grep(r"some adapter kinds offer fewer", intro, ignore_case=True)


def test_event_producer_named_alongside_api_and_event_consumer():
    sec = _downstream_service_branch_section()
    assert grep(r"API Consumer", sec)
    assert grep(r"Event Consumer", sec)
    assert grep(r"Event Producer", sec)
