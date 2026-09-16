"""Doc-shape contract for the /specs glossary artifact (epic #2159, issue #2162).

`ubiquitous-language` enforces terminology consistency only once terms are
already in use. Nothing captured, at spec time, which domain terms were still
undefined — so an unagreed term reached `/plan` looking like an ordinary word.

Note on a correction this slice carries: issue #2162 specifies the Glossary be
added to "both persistence templates... the two templates already mirror each
other". There is only ONE fenced body template; the GitHub-issue branch
composes its body by citing that template's section list rather than
duplicating it. Implementing #2162 literally would have created the second
template — and therefore the drift — its own rationale warns against, so this
slice adds the section to the single template and extends the issue branch's
cited section list. `test_exactly_one_body_template_still_exists` is the guard
that keeps a second one from appearing later.
"""

from __future__ import annotations

import pytest
from skill_doc_helpers import PLUGIN_ROOT, collapsed, grep

SKILL = PLUGIN_ROOT / "skills" / "specs" / "SKILL.md"
GLOSSARY = PLUGIN_ROOT / "skills" / "specs" / "references" / "glossary.md"
PERSISTENCE = PLUGIN_ROOT / "skills" / "specs" / "references" / "persistence.md"


@pytest.fixture(scope="module")
def skill_text() -> str:
    return collapsed(SKILL.read_text())


@pytest.fixture(scope="module")
def glossary_text() -> str:
    return collapsed(GLOSSARY.read_text())


@pytest.fixture(scope="module")
def persistence_raw() -> str:
    return PERSISTENCE.read_text()


# --- one template, not two -------------------------------------------------


def test_exactly_one_body_template_still_exists(persistence_raw):
    """The single-source-template pattern is what this slice preserves."""
    assert persistence_raw.count("```markdown") == 1


def test_the_template_carries_a_glossary_section(persistence_raw):
    assert "## Glossary" in persistence_raw


def test_the_issue_branch_section_list_names_glossary(persistence_raw):
    assert grep(r"Acceptance Criteria, Glossary, Ambiguity Log", persistence_raw)


def test_the_issue_branch_cites_rather_than_copies(persistence_raw):
    assert grep(r"cite it, never copy it", persistence_raw, ignore_case=True)


# --- the row's shape -------------------------------------------------------


@pytest.mark.parametrize("column", ["Term", "Definition", "Status", "Source"])
def test_glossary_row_carries_every_column(persistence_raw, column):
    assert grep(rf"\|\s*{column}\s*\|", persistence_raw)


def test_status_domain_is_exactly_two_valued(persistence_raw):
    assert "`verified` / `unverified`" in persistence_raw


def test_no_third_status_exists(glossary_text):
    assert grep(r"there is no third state", glossary_text, ignore_case=True)


def test_empty_section_is_rendered_not_omitted(persistence_raw):
    assert grep(
        r"render the section even when there is nothing to define",
        persistence_raw,
        ignore_case=True,
    )


# --- verification requires a human ----------------------------------------


def test_verified_requires_a_human_in_the_template(persistence_raw):
    assert grep(r"`verified` means a \*\*human\*\* confirmed", persistence_raw)


def test_skill_states_verified_requires_a_human(skill_text):
    assert grep(r"`verified` requires a human", skill_text)


def test_inferred_definitions_start_unverified(skill_text):
    assert grep(r"the agent inferred starts `unverified`", skill_text, ignore_case=True)


def test_reference_explains_why_an_agent_cannot_self_verify(glossary_text):
    assert grep(
        r"if an agent could self-verify, the status would carry no information",
        glossary_text,
        ignore_case=True,
    )


# --- capture happens in the loop ------------------------------------------


def test_terms_are_captured_while_drafting(skill_text):
    assert grep(r"while drafting", skill_text, ignore_case=True)


def test_reference_rejects_a_separate_pass(glossary_text):
    assert grep(r"not as a separate pass", glossary_text, ignore_case=True)


# --- routing and blocking --------------------------------------------------


def test_unverified_terms_route_through_the_existing_protocol(skill_text):
    assert grep(
        r"routes through the Ambiguity Resolution Protocol",
        skill_text,
        ignore_case=True,
    )


def test_unverified_alone_does_not_block_the_gate(skill_text):
    assert grep(
        r"does not block the Consistency Gate by itself", skill_text, ignore_case=True
    )


def test_reference_distinguishes_blocking_from_non_blocking(glossary_text):
    raw = GLOSSARY.read_text()
    assert "`inferable`" in raw and "`requires-stakeholder-input`" in raw
    assert grep(
        r"blocks only if the protocol classifies it as blocking",
        glossary_text,
        ignore_case=True,
    )


def test_reference_states_why_blocking_on_every_term_would_backfire(glossary_text):
    assert grep(r"route around `/specs` entirely", glossary_text, ignore_case=True)


# --- the unverified -> verified transition --------------------------------


def test_confirming_a_term_resolves_its_log_entry(glossary_text):
    """The transition the acceptance review found had no backing step."""
    assert grep(
        r"flips to `verified` \*\*and\*\* its Ambiguity Log entry is resolved",
        glossary_text,
    )


def test_a_term_cannot_be_verified_while_its_finding_is_open(glossary_text):
    assert grep(
        r"cannot be `verified` while its own finding stays open",
        glossary_text,
        ignore_case=True,
    )


# --- no new machinery ------------------------------------------------------


def test_glossary_lives_inside_the_spec_artifact(skill_text):
    assert grep(
        r"persisted inside the spec artifact",
        collapsed(GLOSSARY.read_text()),
        ignore_case=True,
    )


def test_no_separate_file_or_index_is_created(glossary_text):
    assert grep(r"no separate file, no index", glossary_text, ignore_case=True)


def test_no_new_gate_severity_scheme_or_confidence_score(glossary_text):
    assert grep(
        r"no new gate, severity scheme, or confidence score",
        glossary_text,
        ignore_case=True,
    )
