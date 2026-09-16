"""Doc-shape contract for /specs validate mode (epic #2159, issue #2160).

`/specs` was a collaborative authoring loop only: it assumed the human was
drafting with us right now. A requirements document that already existed and
that we did not help write — a stakeholder PRD, a vendor RFP, a Jira epic —
reached `/plan` unexamined, because the first artifact any gate saw was
already our restatement of it.

Validate mode runs the existing critique categories against the source text
instead. These guards pin the three things that make it trustworthy: the mode
is selected without breaking existing invocations, a path-like argument that
does not resolve is refused rather than silently reinterpreted as prose, and
extraction is distinguishable from inference in the output.
"""

from __future__ import annotations

import pytest
from skill_doc_helpers import PLUGIN_ROOT, collapsed, grep

SKILL = PLUGIN_ROOT / "skills" / "specs" / "SKILL.md"
EXTRACTION = PLUGIN_ROOT / "skills" / "specs" / "references" / "extraction.md"
PERSISTENCE = PLUGIN_ROOT / "skills" / "specs" / "references" / "persistence.md"


@pytest.fixture(scope="module")
def skill_text() -> str:
    return collapsed(SKILL.read_text())


@pytest.fixture(scope="module")
def extraction_text() -> str:
    return collapsed(EXTRACTION.read_text())


@pytest.fixture(scope="module")
def persistence_text() -> str:
    return collapsed(PERSISTENCE.read_text())


# --- mode selection: three branches, not two -------------------------------


def test_mode_is_selected_at_step_0(skill_text):
    assert grep(r"Step 0 — Select the mode", skill_text)


def test_mode_is_selected_without_a_flag(skill_text):
    # A flag would have to be added to every existing invocation.
    assert grep(r"there is no flag", skill_text, ignore_case=True)


def test_prose_invocations_are_explicitly_unaffected(skill_text):
    assert grep(r"unaffected", skill_text, ignore_case=True)
    assert grep(r"authoring.*unchanged", skill_text, ignore_case=True)


def test_all_three_branches_are_present(skill_text):
    for branch in ("validate", "refuse", "authoring"):
        assert grep(rf"\*\*{branch}\*\*", skill_text, ignore_case=True), (
            f"missing {branch!r} branch"
        )


def test_unresolved_path_is_never_reinterpreted_as_prose(skill_text):
    """The blocker the UX review caught: a typo'd path silently became a spec
    description, with no error and no way for the author to notice."""
    assert grep(r"never reinterpreted as prose", skill_text, ignore_case=True)


def test_unfetchable_issue_url_is_covered_too(skill_text):
    assert grep(r"fetch failure|cannot be fetched", skill_text, ignore_case=True)
    assert grep(r"private, deleted, unauthenticated", skill_text, ignore_case=True)


def test_the_selected_mode_is_announced(skill_text):
    assert grep(r"announce the selected mode", skill_text, ignore_case=True)


# --- format refusal --------------------------------------------------------


def test_docx_is_refused_by_name(skill_text):
    assert grep(r"\.docx`? is explicitly out", skill_text, ignore_case=True)


def test_refusal_names_a_reason_and_a_conversion(skill_text):
    assert grep(r"name the reason and the conversion", skill_text, ignore_case=True)


def test_no_partial_parse_is_attempted(skill_text):
    assert grep(r"do not guess at a partial read", skill_text, ignore_case=True)


def test_extraction_reference_repeats_the_no_partial_parse_rule(extraction_text):
    assert grep(r"never attempt a partial parse", extraction_text, ignore_case=True)


# --- citation: extraction must be distinguishable from inference -----------


def test_every_extracted_criterion_cites_its_source(skill_text):
    assert grep(r"cites the source passage", skill_text, ignore_case=True)


def test_an_uncitable_criterion_is_logged_as_an_inference(skill_text):
    assert grep(r"is an inference and is logged", skill_text, ignore_case=True)
    assert grep(
        r"never presented as if the source stated it", skill_text, ignore_case=True
    )


def test_citation_rule_is_detailed_in_the_reference(extraction_text):
    assert grep(
        r"section heading, a line reference, or a short verbatim quote", extraction_text
    )


def test_reference_states_why_citation_matters(extraction_text):
    assert grep(r"indistinguishable", extraction_text, ignore_case=True)


# --- the existing protocol applies unchanged -------------------------------


def test_third_party_documents_block_as_hard(skill_text):
    assert grep(
        r"blocks exactly as hard as an in-house draft", skill_text, ignore_case=True
    )


def test_no_new_gate_or_severity_scheme_is_introduced(extraction_text):
    assert grep(
        r"no new gate, no new severity scheme, no confidence score",
        extraction_text,
        ignore_case=True,
    )


def test_routing_uses_the_existing_two_classifications(extraction_text):
    assert "`inferable`" in EXTRACTION.read_text()
    assert "`requires-stakeholder-input`" in EXTRACTION.read_text()


# --- validate mode stops before /plan --------------------------------------


def test_auto_trigger_is_scoped_to_authoring_mode(persistence_text):
    assert grep(r"authoring mode only", persistence_text, ignore_case=True)


def test_validate_mode_never_auto_invokes(persistence_text):
    assert grep(r"never auto-invoke", persistence_text, ignore_case=True)


def test_printed_message_carries_a_reason_clause(persistence_text):
    """Not merely that the reference explains the design to a maintainer — the
    message the operator sees must name why this run stopped short."""
    assert grep(
        r"printed message must name that reason", persistence_text, ignore_case=True
    )
    assert grep(
        r"wasn't co-authored and approved with you", persistence_text, ignore_case=True
    )


def test_authoring_mode_contract_is_unchanged(persistence_text):
    assert grep(r"do not ask first", persistence_text, ignore_case=True)
