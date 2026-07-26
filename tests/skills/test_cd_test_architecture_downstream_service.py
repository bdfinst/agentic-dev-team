"""Downstream-service branch content-guard tests for
`cd-test-architecture/SKILL.md`. Traces to issue #1434 (sub-issue of epic
#1431) and Steps 1.1/1.2 of the (transient) plan file
plans/issue-1434-cd-test-architecture-downstream-service-branch.md — cite
the issue number alongside the plan path since the plan file is
gitignored/transient (deleted after implementation, per this repo's
CLAUDE.md) and issue #1434 is the durable reference once it's gone.

This file covers Step 1.1 (Step 1's ownership/deployability note), Step 1.2
(the new `#### Downstream-service branch` subsection under Step 4b, plus the
generalized shared Step 4b intro sentence), and Step 1.3 (the downstream-
service branch's Story-shape bullets, the generalized Output-section caveat
cross-reference, and the generalized `test-doubles.md` knowledge-reference
bullet) — plus several corrections beyond the plan's literal Step 1.3 text
(see inline comments on the affected tests).
Assertions here are scoped to the specific section they target, mirroring
the sibling `test_cd_test_architecture_step4b.py`'s scoped-boundary
discipline (a boundary regex must be empirically verified reachable, not
assumed — a prior round of that file family shipped an unreachable boundary
and it was a real bug, issue #1433 round 4).
"""

from __future__ import annotations

from skill_doc_helpers import (
    PLUGIN_ROOT,
    cd_test_architecture_output_section,
    collapsed,
    grep,
    section,
)

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
    Boundary made future-proof for #1435 (arch-review, correctness-review,
    test-smell-review): `^(#### |### 5\\.)` matches whichever comes first.
    Today this subsection is the last `####` sub-heading under Step 4b, so
    the alternation falls through to `^### 5\\.` — the same reachable
    boundary as before. Once #1435 lands its own sibling `#### ` subsection
    after this one, the alternation's first branch takes over and the
    boundary stays correct without another edit — avoiding a repeat of the
    unreachable-boundary bug (#1433 round 4) in the other direction (a
    boundary that becomes wrong, rather than one that was never reachable).
    See `_database_specific_branch_section()` in the sibling file, which
    already made this same class of fix when #1434 landed its own `#### `
    subsection."""
    return section(
        _text(),
        r"^#### Downstream-service branch",
        boundary_pattern=r"^(#### |### 5\.)",
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


def test_step_4b_intro_paragraph_boundary_is_reachable():
    # Empirically verify the scoping boundary actually narrows the text —
    # not an assumption (issue #1433 round 4 lesson) — mirroring the
    # boundary-reachability sanity checks this file already has for
    # `_step_1_section` and `_downstream_service_branch_section`. The
    # intro's own distinguishing content must be present; content past its
    # `#### ` boundary (either branch subsection) must be excluded.
    para = _step_4b_intro_paragraph()
    assert "exactly one of the options listed for that row" in para
    assert "Database-specific branch" not in para
    assert "Downstream-service branch" not in para


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


def test_ownership_classification_not_reasked_at_step_4b_time():
    # AC4: this classification is not itself an interactive question at
    # Step 4b time — it was already recorded at Step 1.
    sec = _downstream_service_branch_section()
    assert grep(r"not re-asked at Step 4b time", sec, ignore_case=True)


def test_downstream_service_branch_reuses_same_batched_prompt_not_a_second_one():
    sec = collapsed(_downstream_service_branch_section())
    assert grep(r"\*?same\*?\s+batched per-run prompt", sec, ignore_case=True)
    assert grep(r"not a second prompt", sec, ignore_case=True)


def test_team_controlled_row_offers_three_options():
    sec = _downstream_service_branch_section()
    # Boundary tightened to match the sibling third-party bullet extraction
    # below (ai-provenance-review, iteration 2) — this asymmetry was
    # previously safe only because the next line happens to be another
    # bullet, which is undocumented and fragile.
    team_controlled_bullet = collapsed(
        section(
            sec,
            r"\*\*Team-controlled\*\*",
            boundary_pattern=r"^(- \*\*|### |\s*$)",
        )
    )
    assert grep(r"Build \(testcontainers\)", team_controlled_bullet)
    assert grep(r"Build \(Fake\)", team_controlled_bullet)
    assert grep(r"Document-only", team_controlled_bullet)


def test_third_party_row_offers_only_two_options_no_testcontainers():
    sec = _downstream_service_branch_section()
    # Boundary tightened (ai-provenance-review, test-review, correctness-
    # review): `^(- \*\*|### )` alone over-captures here — it sweeps past
    # this single bullet through the following "not-offered-option"
    # paragraph and the "Each selected option proposes a Story" lead-in
    # before it reaches the next `- **` bullet. Adding the blank-line
    # alternative stops capture at the first blank-line-then-non-bullet-
    # prose transition, whichever boundary comes first, so this scopes to
    # only the named bullet. The sibling `team_controlled_bullet` extraction
    # above uses this same tightened boundary for consistency (ai-
    # provenance-review, iteration 2).
    third_party_bullet = collapsed(
        section(
            sec,
            r"\*\*Third-party/other-team\*\*",
            boundary_pattern=r"^(- \*\*|### |\s*$)",
        )
    )
    assert grep(r"Build \(Fake\)", third_party_bullet)
    assert grep(r"Document-only", third_party_bullet)
    # Positive supporting text, not just an absence check (#1433's lesson:
    # an unsupported negative is the weakest kind of test). The extraction
    # is already scoped to a single bullet line, so no tightness is needed
    # on the gap between phrases — loosened from a spec-derived-looking
    # `.{0,40}` to `.*` (ai-provenance-review, iteration 2; actual gap in
    # shipped prose is 2 characters).
    assert grep(
        r"Build \(testcontainers\).*is never offered",
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
    # "not a new rule" is anaphoric (referring back to "the same ambiguous-
    # answer rule as any other ambiguous answer above"), but the referent is
    # pinned here: both phrases are asserted against the same `sec` extract,
    # which is the single sentence containing both clauses — reviewed and
    # judged sufficient (ai-provenance-review, iteration 2).
    sec = collapsed(_downstream_service_branch_section())
    assert grep(
        r"same ambiguous-answer rule as any other ambiguous answer",
        sec,
        ignore_case=True,
    )
    assert grep(r"not a new rule", sec, ignore_case=True)


# Guards an out-of-plan fix (issue #1434): beyond the plan's literal Step
# 1.3 text, this also corrects the shared Step 4b intro paragraph's
# misattribution of the option-count variance to "adapter kind" when the
# actual variable is a row's ownership tier (team-controlled vs
# third-party) — cross-cutting adapter kind, not caused by it.
def test_step_4b_intro_no_longer_overclaims_fixed_three_options():
    intro = collapsed(_step_4b_intro_paragraph())
    assert not grep(r"exactly one of three options", intro, ignore_case=True)
    assert grep(
        r"exactly one of the options listed for that row", intro, ignore_case=True
    )
    assert grep(r"up to three", intro, ignore_case=True)
    assert grep(r"ownership tier", intro, ignore_case=True)


def test_event_producer_named_alongside_api_and_event_consumer():
    sec = _downstream_service_branch_section()
    assert grep(r"API Consumer", sec)
    assert grep(r"Event Consumer", sec)
    assert grep(r"Event Producer", sec)


# --- Step 1.3: Story-shape bullets, Output/knowledge-ref generalizations ----

# Mirrors test_cd_test_architecture_step4b.py's DATABASE_FAKE_CAVEAT
# pattern: one reusable constant so the exact verbatim caveat text can't
# drift apart between the two call sites that check it (the Fake Story
# bullet itself, and the assertion that the Output section does NOT
# hardcode it).
# Extends the plan's literal caveat wording to also cite Event Producer
# (issue #1434 iteration 1 fix), since the Downstream-service branch
# explicitly covers Event Producer components and the caveat would
# otherwise cite an incomplete pattern list for those rows — documented
# here since the plan predates this addition.
DOWNSTREAM_FAKE_CAVEAT = (
    "Caveat: this hand-rolled Fake cannot verify that the adapter actually "
    "satisfies the real service's wire contract — pair it with scheduled "
    "provider-contract verification against the provider's real "
    "environment, per the API Consumer / Event Consumer / Event Producer "
    "patterns."
)


def _downstream_testcontainers_bullet() -> str:
    return collapsed(
        section(
            _downstream_service_branch_section(),
            r"\*\*Build \(testcontainers\)\*\* \(team-controlled rows only\)",
            boundary_pattern=r"^- \*\*Build \(Fake\)\*\*",
        )
    )


def _downstream_fake_bullet() -> str:
    return section(
        _downstream_service_branch_section(),
        r"\*\*Build \(Fake\)\*\* \(either tier\)",
        boundary_pattern=r"^- \*\*Document-only\*\*",
    )


def _output_section() -> str:
    return cd_test_architecture_output_section(_text())


def test_testcontainers_story_title_and_description():
    bullet = _downstream_testcontainers_bullet()
    assert grep(
        r"\[<component>\]\s*Add testcontainers-based adapter integration test",
        bullet,
    )
    assert grep(r"real outbound client", bullet, ignore_case=True)
    assert grep(r"component-test-patterns\.md", bullet)


def test_fake_story_title_and_wire_contract_caveat_verbatim():
    bullet = collapsed(_downstream_fake_bullet())
    assert grep(
        r"\[<component>\]\s*Add hand-rolled Fake downstream-service double",
        bullet,
    )
    assert DOWNSTREAM_FAKE_CAVEAT in bullet


def test_fake_story_never_says_mock():
    bullet = _downstream_fake_bullet()
    assert not grep(r"\bmock\b", bullet, ignore_case=True)
    # Positive companion assertion (test-smell-review): the absence check
    # above would still pass even if the whole bullet were deleted, so
    # assert the bullet actually names the Fake it's describing.
    assert grep(r"\bFake\b", bullet)


def test_third_party_fake_additionally_requires_scheduled_verification():
    # Anchored on the literal "**Third-party rows**:" prefix so this scopes
    # to the third-party-specific clause, not the Fake bullet generally.
    bullet = collapsed(_downstream_fake_bullet())
    assert grep(
        r"\*\*Third-party rows\*\*:[^.]*scheduled[^.]*provider-contract "
        r"verification[^.]*(non-prod|real environment)",
        bullet,
        ignore_case=True,
    )
    # Explicitly a companion action, not a fourth option — and no new
    # numbered/labeled top-level option (a literal "4. **...**" item) is
    # introduced alongside the existing 1./2./3. choices in the shared
    # Step 4b intro. Rescoped to `_step_4b_intro_paragraph()` (ai-
    # provenance-review, correctness-review): the previous scope,
    # `_downstream_fake_bullet()`, is a 3-line bullet that could never
    # contain a numbered list, so that check was vacuous — it could never
    # fail even if a real fourth numbered option were added. The numbered
    # 1./2./3. list actually lives in the shared Step 4b intro paragraph.
    assert grep(r"\*\*Third-party rows\*\*:[^.]*not a fourth option", bullet, ignore_case=True)
    assert not grep(r"^\s*4\.\s*\*\*", _step_4b_intro_paragraph())


def test_team_controlled_fake_has_no_scheduled_verification_requirement_stated_positively():
    # Anchored on the literal "**Team-controlled rows**:" prefix so this
    # scopes to the team-controlled-specific clause, not the Fake bullet
    # generally.
    bullet = collapsed(_downstream_fake_bullet())
    # Positive statement, not merely the absence of "scheduled" — #1433's
    # lesson that an unsupported negative is the weakest kind of test.
    # "no such addition" is anaphoric, but the referent is pinned: the
    # regex requires it to appear within the same `[^.]*`-bounded clause as
    # the "**Team-controlled rows**:" anchor, so the extracted match always
    # carries its own referent — reviewed and judged sufficient (ai-
    # provenance-review, iteration 2).
    assert grep(
        r"\*\*Team-controlled rows\*\*:[^.]*carries no such addition",
        bullet,
        ignore_case=True,
    )


def test_output_section_caveat_generalized_not_database_specific():
    sec = _output_section()
    fake_row_clause = collapsed(
        section(
            sec,
            r"row whose status is `Build \(Fake\)`",
            boundary_pattern=r"^### ",
        )
    )
    assert not grep(r"SQL, mapping, or schema", fake_row_clause, ignore_case=True)
    assert DOWNSTREAM_FAKE_CAVEAT not in fake_row_clause
    assert grep(r"Database-specific branch", fake_row_clause)
    assert grep(r"Downstream-service branch", fake_row_clause)
    assert grep(r"branch-specific caveat, verbatim", fake_row_clause, ignore_case=True)


def test_knowledge_references_bullet_covers_both_branches():
    text = _text()
    refs_section = collapsed(
        section(
            text, r"^Grounded in these knowledge references", boundary_pattern=r"^## "
        )
    )
    assert grep(r"test-doubles\.md", refs_section)
    assert grep(
        r"Step 4b's database or downstream-service branch proposes a "
        r"hand-rolled Fake double",
        refs_section,
        ignore_case=True,
    )
    assert not grep(
        r"Step 4b's database branch proposes a hand-rolled Fake double",
        refs_section,
        ignore_case=True,
    )


# Guards an out-of-plan fix (issue #1434): beyond the plan's literal Step
# 1.3 text, this also corrects the shared Step 4b intro paragraph's
# "operator answers" sentence, which previously overclaimed a fixed
# "per-component three-way answer" — generalized alongside the sibling fix
# in test_step_4b_intro_no_longer_overclaims_fixed_three_options above.
def test_step_4b_shared_paragraph_no_longer_overclaims_three_choices():
    intro = collapsed(_step_4b_intro_paragraph())
    assert not grep(r"these three choices", intro, ignore_case=True)
    assert not grep(r"per-component three-way answer", intro, ignore_case=True)
    assert not grep(r"batched three-way question", intro, ignore_case=True)
    assert not grep(r"one of the three labeled options", intro, ignore_case=True)
    assert grep(r"one of the choices listed for that row", intro, ignore_case=True)
    assert grep(r"the batched question", intro, ignore_case=True)
    assert grep(
        r"one of the labeled options for that row", intro, ignore_case=True
    )
    # The "when more than one is offered" qualifier (iteration 1 fix) has no
    # dedicated assertion elsewhere — pin it here alongside this paragraph's
    # other ambiguous-answer wording checks (ai-provenance-review, iteration 2).
    assert grep(r"when more than one is offered", intro, ignore_case=True)
