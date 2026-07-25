"""Doc-shape contract for test-health reading .feature files as a Q2 signal
(issue #1422, Slice 6).

Step 3 (Quadrant coverage) discovers documented Gherkin scenarios via
`detect_bdd_convention.py` and counts them toward Q2 strength independent of
binding status. Step 7 (Classify gaps) emits a `gherkin-gap`-tagged
NO_REFACTOR/REFACTOR_REQUIRED finding for a documented-but-untested
scenario. These are pure content-guard tests over the shipped SKILL.md
prose, matching the pattern in test_low_value_classification.py.
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, grep, grep_multiline, section

TEST_HEALTH = PLUGIN_ROOT / "skills" / "test-health" / "SKILL.md"


def _step_3(text: str) -> str:
    step_3 = section(text, r"^### 3\. Quadrant coverage")
    assert step_3, "Step 3 (Quadrant coverage) section not found in test-health/SKILL.md"
    return step_3


def _step_7(text: str) -> str:
    step_7 = section(text, r"^### 7\. Classify gaps")
    assert step_7, "Step 7 (Classify gaps) section not found in test-health/SKILL.md"
    return step_7


# --- Step 6.1: .feature discovery as a Q2 signal ----------------------------


def test_step_3_mentions_detect_bdd_convention_script():
    step_3 = _step_3(TEST_HEALTH.read_text(encoding="utf-8"))
    assert grep(r"detect_bdd_convention\.py", step_3)


def test_step_3_mentions_feature_file_discovery():
    step_3 = _step_3(TEST_HEALTH.read_text(encoding="utf-8"))
    assert grep(r"\.feature", step_3)
    assert grep(r"Scenario", step_3)


def test_step_3_names_q2_as_the_signal_target():
    step_3 = _step_3(TEST_HEALTH.read_text(encoding="utf-8"))
    assert grep(r"Q2", step_3)


def test_step_3_documents_the_documented_but_not_yet_bound_distinction():
    # A documented scenario counts toward Q2 strength whether or not it is
    # yet bound to a runnable test — binding status is Step 7's concern.
    step_3 = _step_3(TEST_HEALTH.read_text(encoding="utf-8"))
    assert grep(r"not yet bound|whether or not it is yet bound", step_3, ignore_case=True)


def test_step_3_documents_the_no_signal_fallback():
    step_3 = _step_3(TEST_HEALTH.read_text(encoding="utf-8"))
    assert grep(r"no signal", step_3, ignore_case=True)


def test_step_3_absent_signal_produces_no_placeholder_language():
    # The fallback sentence must describe silent absence, not an error or a
    # placeholder ("N/A", "TODO", etc.) rendered into the report.
    step_3 = _step_3(TEST_HEALTH.read_text(encoding="utf-8"))
    assert not grep(r"\bTODO\b", step_3)
    assert not grep(r"\bN/A\b", step_3)


# --- Step 6.2: gherkin-gap NO_REFACTOR/REFACTOR_REQUIRED class --------------


def test_step_7_names_the_gherkin_gap_tag():
    step_7 = _step_7(TEST_HEALTH.read_text(encoding="utf-8"))
    assert grep(r"gherkin-gap", step_7)


def test_step_7_documents_the_no_refactor_refactor_required_split():
    # The split condition is "needs a testability seam first" (REFACTOR_REQUIRED)
    # vs. "behavior already exists, test can be added as-is" (NO_REFACTOR) — NOT
    # "doesn't exist yet", which is NOT_IMPLEMENTED's condition, a third and
    # non-actionable class (see test_step_7_routes_not_yet_implemented_scenarios_
    # away_from_refactor_required below). A prior version of this test asserted
    # on "doesn't exist yet" here, which passed identically whether that phrase
    # was bound to REFACTOR_REQUIRED (the old, now-wrong contract) or to
    # NOT_IMPLEMENTED (the fixed contract) — it could not tell the two apart.
    step_7 = _step_7(TEST_HEALTH.read_text(encoding="utf-8"))
    assert grep(r"NO_REFACTOR", step_7)
    assert grep(r"REFACTOR_REQUIRED", step_7)
    assert grep_multiline(
        r"REFACTOR_REQUIRED.{0,120}needs a testability seam first", step_7
    )
    assert grep_multiline(
        r"NO_REFACTOR.{0,120}behavior already exists in production code", step_7
    )


def test_step_7_pins_the_gherkin_gap_meaning_sentence():
    step_7 = _step_7(TEST_HEALTH.read_text(encoding="utf-8"))
    assert (
        "documented Gherkin scenario '<title>' has no bound step-definition "
        "or cited test yet." in step_7
    )


def test_step_7_pins_the_gherkin_gap_action_sentence():
    step_7 = _step_7(TEST_HEALTH.read_text(encoding="utf-8"))
    assert (
        "implement the missing binding/test before treating this area as "
        "low-risk." in step_7
    )


def test_step_7_routes_not_yet_implemented_scenarios_away_from_refactor_required():
    # domain-review: REFACTOR_REQUIRED must mean "needs a seam", never
    # "behavior doesn't exist" — Phase 7 only introduces seams, so a
    # NOT_IMPLEMENTED scenario classified REFACTOR_REQUIRED would dead-end
    # there with nothing to refactor. Bound with grep_multiline (not grep)
    # since these phrases are long enough that a markdown reflow could move
    # them across a line wrap with no semantic change.
    step_7 = _step_7(TEST_HEALTH.read_text(encoding="utf-8"))
    assert grep(r"`NOT_IMPLEMENTED`", step_7)
    assert grep_multiline(
        r"classify it `NOT_IMPLEMENTED` instead.{0,60}neither `NO_REFACTOR`"
        r"[[:space:]]+nor.{0,20}`REFACTOR_REQUIRED`[[:space:]]+applies",
        step_7,
        ignore_case=True,
    )
    assert grep(r"feature gap", step_7, ignore_case=True)
    assert grep(r"product backlog", step_7, ignore_case=True)
    assert grep_multiline(
        r"dead-end[[:space:]]+there[[:space:]]+with[[:space:]]+no[[:space:]]+seam"
        r"[[:space:]]+to[[:space:]]+introduce",
        step_7,
        ignore_case=True,
    )


def test_step_7_documents_the_existence_discriminator_and_ambiguity_default():
    # domain-review: the exists/doesn't-exist split needs a tie-breaker for
    # partial implementation and genuine ambiguity, or every auditor invents
    # their own rule. Default-to-NOT_IMPLEMENTED-on-ambiguity is the safer
    # direction: an over-classified feature gap is inert and visible in the
    # report, while an over-classified REFACTOR_REQUIRED dead-ends at Phase 7.
    step_7 = _step_7(TEST_HEALTH.read_text(encoding="utf-8"))
    assert grep(r"`Then` outcome, not the", step_7)
    assert grep(r"Scenario Outline", step_7)
    assert grep_multiline(
        r"ambiguous.{0,60}default to.{0,5}`NOT_IMPLEMENTED`", step_7, ignore_case=True
    )


def test_step_7_notes_gherkin_gap_can_never_be_low_value():
    # A documented scenario has an observable outcome by construction, so it
    # always fails LOW_VALUE criterion 2 ("no observable outcome").
    step_7 = _step_7(TEST_HEALTH.read_text(encoding="utf-8"))
    assert grep(r"LOW_VALUE", step_7)
    assert grep(r"observable outcome", step_7, ignore_case=True)
    assert grep(r"criterion 2|criteria 2", step_7, ignore_case=True)
