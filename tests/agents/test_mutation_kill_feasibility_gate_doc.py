"""Doc-content contract for the mutation-kill agent's pre-loop feasibility
gate (#1543, split out of ``test_mutation_kill_agent.py`` per #1564).

Mirrors the grep-on-section pattern already used in
``test_mutation_kill_baseline_reuse_doc.py`` (itself split out from
``test_mutation_kill_agent.py`` for the baseline-reuse procedure, #1545) —
pure text assertions over shipped agent prose, no state-mutating filesystem/
git operations. Reuses ``skill_doc_helpers.section()`` for section-scoped
extraction rather than hand-rolling a new one, per this repo's established
DRY convention.

Issue #1543: split the pre-loop feasibility gate's single ``degrade`` bullet
into the unconditional shim-decline/capture-failure degrade and a new
``ask-operator`` outcome for the budget-only case.
"""

from __future__ import annotations

import re

import pytest
from _mutation_kill_agent_doc_helpers import agent_text, required_section
from skill_doc_helpers import collapsed


@pytest.fixture(scope="module")
def text() -> str:
    return agent_text()


@pytest.fixture(scope="module")
def feasibility_section(text: str) -> str:
    return required_section(
        text,
        r"^## Pre-loop feasibility gate",
        boundary_pattern=r"^## ",
        include_start_line=False,
        name="Pre-loop feasibility gate",
    )


@pytest.fixture(scope="module")
def feasibility_flat(feasibility_section: str) -> str:
    return collapsed(feasibility_section)


def test_ask_operator_is_an_outcome_distinct_from_degrade(
    feasibility_section: str,
) -> None:
    assert "ask-operator" in feasibility_section
    assert "degrade" in feasibility_section
    assert re.search(
        r"distinct.*third outcome|third.*outcome|two separate outcomes",
        feasibility_section,
        re.IGNORECASE,
    )


def test_auto_degrade_is_unconditional_for_two_hard_blockers(
    feasibility_flat: str,
) -> None:
    assert re.search(
        r"unconditional.{0,20}for the two hard blockers", feasibility_flat
    )


def test_auto_degrade_covers_shim_decline_referenced_by_1160(
    feasibility_flat: str,
) -> None:
    assert re.search(r"shim.{0,20}#1160", feasibility_flat)


def test_auto_degrade_covers_capture_probe_failure_referenced_by_1157(
    feasibility_flat: str,
) -> None:
    assert re.search(r"capture.{0,20}probe.{0,20}#1157", feasibility_flat)


def test_budget_alone_is_not_a_hard_blocker(feasibility_flat: str) -> None:
    # Budget alone must never be named as an unconditional-degrade trigger.
    assert re.search(r"not a hard blocker|is not a hard blocker", feasibility_flat)
    # Retired behavior must be gone, not just supplemented: budget alone
    # unconditionally degrading (the pre-#1543 shape) must not reappear.
    assert not re.search(
        r"budget.{0,30}(alone|only).{0,30}unconditional.{0,20}degrade",
        feasibility_flat,
        re.IGNORECASE,
    )


def test_confirmation_prompt_uses_human_readable_duration_term(
    feasibility_section: str,
) -> None:
    assert re.search(r"human-readable", feasibility_section, re.IGNORECASE)


def test_confirmation_prompt_never_shows_raw_seconds(feasibility_flat: str) -> None:
    assert re.search(r"never raw seconds", feasibility_flat, re.IGNORECASE)


def test_confirmation_prompt_duration_cites_scope_file_count(
    feasibility_flat: str,
) -> None:
    assert re.search(r"scope-file count", feasibility_flat)


def test_confirmation_prompt_duration_cites_per_file_probe_seconds(
    feasibility_flat: str,
) -> None:
    assert re.search(r"per-file probe seconds", feasibility_flat)


def test_confirmation_prompt_names_proceed_anyway_label(
    feasibility_section: str,
) -> None:
    assert re.search(r"proceed anyway", feasibility_section, re.IGNORECASE)


def test_confirmation_prompt_proceed_anyway_reenters_loop(
    feasibility_flat: str,
) -> None:
    assert re.search(r"re-enters the loop for this invocation", feasibility_flat)


def test_confirmation_prompt_names_degrade_consequence(
    feasibility_flat: str,
) -> None:
    assert re.search(
        r"single advisory pass \(score only.{0,40}no mutants killed.{0,20}no commits",
        feasibility_flat,
        re.IGNORECASE,
    )


def test_agent_echoes_back_chosen_path_before_acting(
    feasibility_flat: str,
) -> None:
    assert re.search(
        r"echo back which path.*before acting", feasibility_flat, re.IGNORECASE
    )


def test_off_script_reply_is_reasked_never_guessed(feasibility_flat: str) -> None:
    assert re.search(
        r"matching neither documented choice.{0,20}re-asked.{0,60}"
        r"same two choices restated",
        feasibility_flat,
        re.IGNORECASE,
    )
    assert re.search(r"never default or guess", feasibility_flat, re.IGNORECASE)


def test_non_interactive_session_triggers_default_to_degrade(
    feasibility_flat: str,
) -> None:
    assert re.search(
        r"non-interactive session.{0,40}no usable tty.{0,20}no operator available",
        feasibility_flat,
        re.IGNORECASE,
    )


def test_non_interactive_default_choice_is_degrade(feasibility_flat: str) -> None:
    assert re.search(r"default to `?degrade`?", feasibility_flat, re.IGNORECASE)


def test_non_interactive_auto_decision_logged_same_way(
    feasibility_flat: str,
) -> None:
    assert re.search(
        r"log the auto-decision.{0,20}the same way", feasibility_flat, re.IGNORECASE
    )
