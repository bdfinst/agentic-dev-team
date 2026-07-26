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
    collapsed,
    grep,
    section,
)

SKILL = PLUGIN_ROOT / "skills" / "cd-test-architecture" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text(encoding="utf-8")


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


def test_event_producer_named_alongside_api_and_event_consumer():
    sec = _downstream_service_branch_section()
    assert grep(r"API Consumer", sec)
    assert grep(r"Event Consumer", sec)
    assert grep(r"Event Producer", sec)



