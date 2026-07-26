"""Downstream-service branch content-guard tests for
`cd-test-architecture/SKILL.md`. Traces to issue #1434 (sub-issue of epic
#1431) and the (transient) plan file
plans/issue-1434-cd-test-architecture-downstream-service-branch.md — cite
the issue number alongside the plan path since the plan file is
gitignored/transient (deleted after implementation, per this repo's
CLAUDE.md) and issue #1434 is the durable reference once it's gone.

This file covers the `#### Downstream-service branch` subsection under
Step 4b: every row offers all three options uniformly (no ownership-based
distinction — a corrected design, reversing an original build that gated
`Build (testcontainers)` on a team-controlled/third-party classification;
see the plan's "Design Revision" section), the universal out-of-band/
scheduled validation-placement rule, and the branch's Story-shape bullets,
Output-section caveat cross-reference, and `test-doubles.md`
knowledge-reference bullet.
Assertions here are scoped to the specific section they target, mirroring
the sibling `test_cd_test_architecture_step4b.py`'s scoped-boundary
discipline (a boundary regex must be empirically verified reachable, not
assumed — a prior round of that file family shipped an unreachable boundary
and it was a real bug, issue #1433 round 4).
"""

from __future__ import annotations

from skill_doc_helpers import (
    PLUGIN_ROOT,
    cd_test_architecture_downstream_service_branch_section,
    cd_test_architecture_fake_row_clause,
    collapsed,
    grep,
    section,
)

SKILL = PLUGIN_ROOT / "skills" / "cd-test-architecture" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text(encoding="utf-8")


def _downstream_service_branch_section() -> str:
    """Scoped to the `#### Downstream-service branch` subsection. Promoted
    (issue #1435, Step 1.3) to the shared
    `cd_test_architecture_downstream_service_branch_section` helper in
    `skill_doc_helpers.py` after `test_cd_test_architecture_virtual_service_
    libraries.py` needed the identical extraction — see that helper's
    docstring for the boundary-reachability rationale (#1433 round 4,
    #1434's `_database_specific_branch_section()` precedent)."""
    return cd_test_architecture_downstream_service_branch_section(_text())


def _step_1_section() -> str:
    """Scoped to `### 1. Inventory the application's components`, up to the
    next top-level step. Restored (ai-provenance-review, issue #1434 AC2):
    the equivalent helper was removed along with the reverted ownership
    sentence during Step 1.1, leaving AC2 ("Step 1 is NOT amended with any
    ownership/deployability recording instruction") with zero test
    coverage."""
    return section(_text(), r"^### 1\. Inventory", boundary_pattern=r"^### 2\.")


def test_step_1_lists_component_patterns_with_no_ownership_classification():
    # AC2 regression guard: pins the actual reverted wording (via
    # `git show 168a80b:plugins/dev-team/skills/cd-test-architecture/SKILL.md`)
    # rather than guessing. That commit's Step 1 sentence read: "For each API
    # Consumer, Event Consumer, or Event Producer component, also record
    # whether the dependency is team-controlled (in-house, containerizable)
    # or third-party/other-team, per `component-test-patterns.md`'s
    # ownership guidance." Note: "deployab" is deliberately NOT used as a
    # guard substring here — Step 1's pre-existing, unrelated "Map the
    # deployable/testable surfaces" sentence (present both before and after
    # the ownership sentence was ever added) legitimately contains that
    # substring, so banning it would fail against correct, unrelated text.
    # "team-controlled" / "third-party" / "ownership guidance" are the
    # actual reverted phrasing and aren't used anywhere else in Step 1.
    sec = _step_1_section()
    assert grep(r"API Consumer", sec)
    assert grep(r"Event Consumer", sec)
    assert grep(r"Event Producer", sec)
    assert grep(r"User Interface", sec)
    assert grep(r"Stateful Service", sec)
    assert not grep(r"team-controlled", sec, ignore_case=True)
    assert not grep(r"third-party", sec, ignore_case=True)
    assert not grep(r"ownership guidance", sec, ignore_case=True)
    assert not grep(r"record whether the dependency", sec, ignore_case=True)


# --- Boundary reachability sanity check -------------------------------------


def test_downstream_service_branch_section_boundary_is_reachable():
    # structure-review + correctness-review + ai-provenance-review +
    # test-review (confirmed by all four): this header had no test beneath
    # it after the old Step-1 boundary test was removed during the revert.
    # Restore a real boundary-reachability check: the extracted section
    # must exclude the next step's content, proving the boundary_pattern
    # actually stops the extraction rather than running to end-of-file.
    sec = _downstream_service_branch_section()
    assert not grep(r"### 5\. Produce a migration path", sec)
    assert not grep(r"Order the moves from current", sec)


# --- Step 1.2: Downstream-service branch ------------------------------------


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


def test_downstream_service_row_offers_all_three_options_uniformly():
    # Every row offers all three options identically — no ownership-based
    # row-shape distinction anywhere in the subsection (operator correction,
    # issue #1434: reverses the original build's team-controlled/third-party
    # split).
    sec = _downstream_service_branch_section()
    assert grep(r"Build \(testcontainers\)", sec)
    assert grep(r"Build \(Fake\)", sec)
    assert grep(r"Document-only", sec)
    # "team-controlled"/"third-party" still appear in the subsection — but
    # only inside the "runs out-of-band regardless of ownership" placement
    # rule, not as a row-shape/option-count gate. Assert the no-distinction
    # framing positively rather than banning the words outright.
    assert grep(r"no ownership-based distinction", sec, ignore_case=True)
    assert grep(r"every row offers all three options identically", sec, ignore_case=True)


def test_downstream_service_branch_states_all_validation_is_scheduled_out_of_band():
    # Positive supporting text (#1433's lesson: an unsupported negative is
    # the weakest kind of test) that all off-gate validation — regardless of
    # ownership — runs out-of-band, on a schedule, never pre-merge/in-band.
    sec = collapsed(_downstream_service_branch_section())
    assert grep(r"out-of-band", sec, ignore_case=True)
    assert grep(r"on a schedule", sec, ignore_case=True)
    assert grep(r"never pre-merge/in-band", sec, ignore_case=True)
    assert grep(
        r"regardless of whether the dependency is team-controlled or third-party",
        sec,
        ignore_case=True,
    )


def test_universal_placement_rule_cites_consistent_knowledge_file_guidance():
    # correctness-review + ai-provenance-review (confirmed independently)
    # originally found SKILL.md's universal placement rule citing a
    # component-test-patterns.md/cd-test-architecture.md ownership-tiered
    # rule that contradicted it (team-controlled deps Stage 1/2 in-band,
    # third-party out-of-band). Rather than adding an "override" caveat,
    # both knowledge files were corrected to state the same universal
    # out-of-band/scheduled-regardless-of-ownership rule (see
    # component-test-patterns.md's API Consumer/Event Consumer/Event
    # Producer Pipeline lines and cd-test-architecture.md's Integration row
    # + Pre-Merge Gate Rule section) — so SKILL.md's citation is now a
    # plain, accurate reference, not an override. This test guards that the
    # citation names both files and doesn't reintroduce override language.
    sec = collapsed(_downstream_service_branch_section())
    assert grep(r"component-test-patterns\.md", sec)
    assert grep(r"cd-test-architecture\.md", sec)
    assert grep(r"placement rule", sec, ignore_case=True)
    assert not grep(r"overrides", sec, ignore_case=True)
    assert not grep(r"narrows", sec, ignore_case=True)


def _component_test_patterns_text() -> str:
    return (
        (PLUGIN_ROOT / "knowledge" / "component-test-patterns.md")
        .read_text(encoding="utf-8")
    )


def _cd_test_architecture_knowledge_text() -> str:
    return (
        (PLUGIN_ROOT / "knowledge" / "cd-test-architecture.md")
        .read_text(encoding="utf-8")
    )


def test_knowledge_files_state_the_universal_out_of_band_rule():
    # ai-provenance-review: SKILL.md:127 cites component-test-patterns.md
    # and cd-test-architecture.md as the authority for the universal
    # out-of-band/scheduled-regardless-of-ownership placement rule, but
    # nothing previously read either file — the citation was load-bearing
    # and unguarded, so reverting either knowledge file back to the old
    # ownership-tiered wording would break SKILL.md's citation's truth
    # with a fully green suite. Pin the corrected wording directly.
    patterns_text = _component_test_patterns_text()
    # API Consumer, Event Consumer, Event Producer Pipeline lines each
    # state adapter integration runs out-of-band on a schedule, with
    # wording that varies slightly per line but always names both
    # ownership tiers as covered by the same rule.
    assert grep(
        r"adapter integration out-of-band on a schedule.*never in-band",
        patterns_text,
        ignore_case=True,
    )
    assert grep(
        r"regardless of whether the dependency is in-house or "
        r"third-party/other-team",
        patterns_text,
        ignore_case=True,
    )
    assert grep(
        r"regardless of whether the broker is team-controlled or "
        r"managed/third-party",
        patterns_text,
        ignore_case=True,
    )
    assert not grep(
        r"adapter integration for \*\*in-house\*\* deps", patterns_text
    )
    assert not grep(r"adapter integration vs team-controlled broker", patterns_text)
    # ai-provenance-review (round 2): the prior version of this test only
    # positively guarded API Consumer/Event Consumer — the sibling patterns
    # also converted to the universal rule (API Provider, Event Producer,
    # Stateful Service, Scheduled Job) had no positive assertion, so
    # reverting any of them individually would leave this test green.
    assert grep(
        r"adapter integration out-of-band on a schedule, regardless of "
        r"ownership; provider contract verification",
        patterns_text,
        ignore_case=True,
    )
    assert grep(
        r"adapter integration out-of-band on a schedule, regardless of "
        r"ownership; post-deploy synthetic",
        patterns_text,
        ignore_case=True,
    )
    assert grep(
        r"cluster tests out-of-band on a schedule, regardless of ownership",
        patterns_text,
        ignore_case=True,
    )
    assert grep(
        r"adapter integration out-of-band on a schedule, regardless of "
        r"ownership; small deployed-binary set out-of-band",
        patterns_text,
        ignore_case=True,
    )

    arch_text = _cd_test_architecture_knowledge_text()
    assert grep(
        r"Out-of-band / scheduled, regardless of ownership", arch_text
    )
    assert grep(r"Out-of-band / scheduled, always", arch_text)
    assert not grep(
        r"Stage 1/2 for team-controlled containers", arch_text
    )
    assert not grep(
        r"Adapter integration test\*\* \(Stage 1/2\).*for dependencies you "
        r"control",
        arch_text,
    )
    # ai-provenance-review (round 2): Double Validation item 3's fix
    # (out-of-band/scheduled, regardless of ownership) previously had only
    # the negative check above — add the positive companion.
    assert grep(
        r"out-of-band, on a schedule\s*—\s*never in-band, regardless of "
        r"ownership",
        arch_text,
        ignore_case=True,
    )


def test_ambiguous_answer_rule_reused_not_reinvented():
    # "not a new rule" is anaphoric (referring back to "the same ambiguous-
    # answer rule as any other ambiguous answer above"). A single anchored
    # regex spanning both clauses pins the anaphoric referent directly,
    # rather than two independent asserts against the whole subsection
    # (which could each match a different sentence and not actually prove
    # the two clauses are joined).
    sec = collapsed(_downstream_service_branch_section())
    assert grep(
        r"same ambiguous-answer rule as any other ambiguous answer "
        r"above\s*—\s*not a new rule",
        sec,
        ignore_case=True,
    )


def test_event_producer_named_alongside_api_and_event_consumer():
    sec = _downstream_service_branch_section()
    assert grep(r"API Consumer", sec)
    assert grep(r"Event Consumer", sec)
    assert grep(r"Event Producer", sec)


# --- Step 1.3: Story-shape bullets, Output/knowledge-ref generalizations ----

# One reusable constant so the exact verbatim caveat text can't drift apart
# between the two call sites that check it (the Fake Story bullet itself,
# and the assertion that the Output section does NOT hardcode it) — mirrors
# test_cd_test_architecture_step4b.py's DATABASE_FAKE_CAVEAT pattern. Cites
# all three component patterns (API Consumer / Event Consumer / Event
# Producer) since the branch covers all three uniformly, with no ownership
# distinction to justify a narrower citation.
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
            r"\*\*Build \(testcontainers\)\*\*",
            boundary_pattern=r"^- \*\*Build \(Fake\)\*\*",
        )
    )


def _downstream_fake_bullet() -> str:
    return section(
        _downstream_service_branch_section(),
        r"\*\*Build \(Fake\)\*\*",
        boundary_pattern=r"^- \*\*Document-only\*\*",
    )


def test_testcontainers_story_title_and_description():
    bullet = _downstream_testcontainers_bullet()
    assert grep(
        r"\[<component>\]\s*Add testcontainers-based adapter integration test",
        bullet,
    )
    assert grep(r"real outbound client", bullet, ignore_case=True)
    assert grep(r"out-of-band on a schedule", bullet, ignore_case=True)
    assert grep(r"component-test-patterns\.md", bullet)


def test_1435_reference_is_a_maintainer_note_not_emitted_story_content():
    # ai-provenance-review (still unresolved after a prior fix pass): the
    # #1435 issue reference was embedded inside the sentence describing
    # the emitted Story's own description, so a skill run in a downstream
    # user's repo could copy "#1435" verbatim into that user's Story,
    # where the number is meaningless. Moved to a clearly-parenthetical
    # trailing sentence explicitly labeled as a maintainer note.
    #
    # `section()`'s boundary matching is line-granular (the whole bullet
    # is one unwrapped source line, per this SKILL.md's style), so it
    # can't split "Its description..." from "(This bullet is a
    # placeholder..." within that single line — use a plain string split
    # on the bullet text instead.
    bullet = collapsed(_downstream_testcontainers_bullet())
    assert grep(r"maintainer note, not emitted Story content", bullet, ignore_case=True)
    marker = "(This bullet is a placeholder"
    assert marker in bullet
    description_clause = bullet.split(marker, 1)[0]
    assert "#1435" not in description_clause


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


def test_fake_story_always_requires_scheduled_verification_no_ownership_exemption():
    # "scheduled" + "provider-contract verification" appear unconditionally
    # in the Fake bullet — no ownership-based exemption anywhere in this
    # subsection (operator correction, issue #1434: reverses the original
    # build's team-controlled exemption from this requirement).
    bullet = collapsed(_downstream_fake_bullet())
    assert grep(r"scheduled", bullet, ignore_case=True)
    assert grep(r"provider-contract verification", bullet, ignore_case=True)
    assert grep(r"not a fourth option", bullet, ignore_case=True)
    sec = _downstream_service_branch_section()
    assert not grep(r"team-controlled rows", sec, ignore_case=True)
    assert not grep(r"third-party rows", sec, ignore_case=True)
    # Positive companion (test-smell-review): the two negative assertions
    # above guard the real prior wording (git show 168a80b confirms
    # "**Third-party rows**:" / "**Team-controlled rows**:" were the actual
    # bolded labels pre-revert), but a positive assertion proves the current
    # subsection actually states the no-distinction framing rather than
    # simply omitting the old labels.
    assert grep(r"no ownership-based distinction", sec, ignore_case=True)


def _downstream_document_only_bullet() -> str:
    # No boundary_pattern is passed deliberately: `Document-only` is the
    # last bullet in `_downstream_service_branch_section()`'s own
    # already-truncated text, so any boundary_pattern here would be
    # structurally unreachable — that already-truncated text has no
    # further `#### `/`### 5.` line for it to match (ai-provenance-review:
    # the prior boundary_pattern=r"^(#### |### 5\.)" could never fire,
    # the same unreachable-boundary class this file's docstring warns
    # against, just silently harmless here because there's nothing past
    # this bullet to over-capture). Extraction correctly runs to the end
    # of the outer section instead.
    return collapsed(
        section(
            _downstream_service_branch_section(),
            r"\*\*Document-only\*\*",
        )
    )


def test_downstream_service_branch_document_only_is_report_only_noop():
    # Mirrors test_database_branch_document_only_is_report_only_noop in the
    # sibling file — the bare "Document-only" label was already checked
    # (test_downstream_service_row_offers_all_three_options_uniformly), but
    # its bullet body content had no assertion of its own (test-review gap).
    bullet = _downstream_document_only_bullet()
    assert grep(r"document-only", bullet, ignore_case=True)
    assert grep(r"report only", bullet, ignore_case=True)
    assert grep(r"no further action", bullet, ignore_case=True)


def test_output_section_caveat_generalized_not_database_specific():
    fake_row_clause = cd_test_architecture_fake_row_clause(_text())
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


