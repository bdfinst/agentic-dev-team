"""Doc-shape contract for the predictability check (epic #2159, issue #2163).

The Ambiguity Resolution Protocol names its own failure mode: spec synthesis
tends to produce "decisions that look thorough while encoding the same
happy-path assumptions a direct implementation would make silently."
`inferable` is where that lands — an assumption is waved through because it
reads as natural, and naturalness is explicitly not the test.

The check makes an assumption falsifiable at the point it is classified: name
one plausible alternative outcome and ask whether the source rules it out.

These guards pin the four things that keep it from becoming either a rubber
stamp or a false-block generator: placement between Steps A and B, "at most
one candidate evaluated" rather than "one manufactured every time", rejection
of absurd candidates, and recording on a pass as well as a flip.
"""

from __future__ import annotations

import pytest
from skill_doc_helpers import PLUGIN_ROOT, collapsed, grep

SKILL = PLUGIN_ROOT / "skills" / "specs" / "SKILL.md"
REFERENCE = PLUGIN_ROOT / "skills" / "specs" / "references" / "predictability-check.md"


@pytest.fixture(scope="module")
def skill_text() -> str:
    return collapsed(SKILL.read_text())


@pytest.fixture(scope="module")
def reference_text() -> str:
    return collapsed(REFERENCE.read_text())


# --- placement between Step A and Step B ----------------------------------


def test_the_reference_exists():
    assert REFERENCE.is_file()


def test_check_sits_between_step_a_and_step_b():
    """Structural, not merely asserted: its output is a classification, so it
    must run after inference is attempted and before one is recorded."""
    raw = SKILL.read_text()
    assert raw.index("**Step A — Attempt inference.**") < raw.index(
        "**Step A2 — Predictability check.**"
    )
    assert raw.index("**Step A2 — Predictability check.**") < raw.index(
        "**Step B — Classify the finding.**"
    )


def test_reference_states_it_runs_during_classification(reference_text):
    assert grep(
        r"during\*? classification, not a separate pass",
        reference_text,
        ignore_case=True,
    )


# --- at most one candidate, evaluated -------------------------------------


def test_skill_says_at_most_one_not_exactly_one(skill_text):
    assert grep(r"at most\*?\*? one", skill_text, ignore_case=True)


def test_skill_does_not_say_exactly_one(skill_text):
    """The original wording contradicted absurd-candidate rejection: if the only
    candidate was absurd, 'exactly one' forced manufacturing a bad one."""
    assert not grep(r"exactly one plausible alternative", skill_text, ignore_case=True)


def test_reference_rejects_the_quota_reading(reference_text):
    assert grep(r"not always one, manufactured", reference_text, ignore_case=True)
    assert grep(
        r"does not manufacture a bad one to satisfy a quota",
        reference_text,
        ignore_case=True,
    )


def test_reference_calls_it_a_tripwire_not_an_enumeration(reference_text):
    assert grep(r"tripwire, not an enumeration", reference_text, ignore_case=True)


def test_no_plausible_alternative_case_is_covered(reference_text):
    assert grep(r"no plausible alternative exists", reference_text, ignore_case=True)


# --- the flip condition ----------------------------------------------------


def test_unruled_out_alternative_forces_stakeholder_input(skill_text):
    assert grep(
        r"does not rule it out, classify `requires-stakeholder-input`",
        skill_text,
        ignore_case=True,
    )


def test_ruled_out_alternative_stays_inferable(reference_text):
    assert grep(
        r"stays `inferable`, and the check is recorded as passed",
        reference_text,
        ignore_case=True,
    )


# --- plausible, not absurd -------------------------------------------------


def test_absurd_candidates_are_rejected(reference_text):
    assert grep(r"plausible, not absurd", reference_text, ignore_case=True)


def test_reference_states_why_absurd_candidates_are_harmful(reference_text):
    assert grep(
        r"false blocks are how a gate gets ignored", reference_text, ignore_case=True
    )


def test_reference_names_the_deliberate_divergence_from_defospam(reference_text):
    assert grep(
        r"advisory tool whose findings are suggestions",
        reference_text,
        ignore_case=True,
    )


def test_alternative_must_be_shippable(reference_text):
    assert grep(
        r"a competent developer could actually ship", reference_text, ignore_case=True
    )


# --- recording, including on a pass ---------------------------------------


def test_skill_requires_recording_every_time(skill_text):
    assert grep(
        r"record the outcome in the Ambiguity Log row every time, pass included",
        skill_text,
        ignore_case=True,
    )


def test_reference_tabulates_all_three_outcomes(reference_text):
    for outcome in ("Flipped to", "Stayed `inferable`", "No plausible alternative"):
        assert grep(rf"\|\s*{outcome}", reference_text, ignore_case=True), (
            f"missing outcome row: {outcome!r}"
        )


def test_reference_states_why_a_silent_pass_is_harmful(reference_text):
    assert grep(
        r"omitted check is indistinguishable from a skipped one",
        reference_text,
        ignore_case=True,
    )


def test_flipped_rows_record_the_alternative_as_the_question(reference_text):
    assert grep(
        r"it is the question the human is being asked", reference_text, ignore_case=True
    )


# --- division of labor with plan-review-acceptance ------------------------


def test_skill_names_the_boundary(skill_text):
    assert grep(
        r"does not duplicate `plan-review-acceptance`", skill_text, ignore_case=True
    )


def test_reference_states_why_the_earlier_placement_matters(reference_text):
    assert grep(
        r"placement, and placement is the whole point", reference_text, ignore_case=True
    )
    assert grep(r"the later one structurally cannot", reference_text, ignore_case=True)


def test_reference_acknowledges_what_the_later_check_still_owns(reference_text):
    assert grep(r"still owns weasel-word detection", reference_text, ignore_case=True)


def test_no_new_gate_severity_scheme_or_confidence_score(reference_text):
    assert grep(
        r"no new gate, severity scheme, or confidence score",
        reference_text,
        ignore_case=True,
    )


def test_check_only_moves_items_between_existing_classifications(reference_text):
    assert grep(
        r"only moves items between the two existing classifications",
        reference_text,
        ignore_case=True,
    )
