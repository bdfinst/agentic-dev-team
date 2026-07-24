"""Doc-shape contract for issue #1396 / plans/descriptive-step-back-references.md
(Slice 1): bare prose back-references to numbered steps (e.g. "(Step 2b)")
are relabeled to name the step's action inline, and two wrong-step-number
bugs in session-review/SKILL.md ("Step 2b" for what is actually "3b";
"Step 0" for what is actually "1") are corrected. Step *headings* are
untouched everywhere — only prose back-references change.
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT

CD_TEST_ARCHITECTURE = PLUGIN_ROOT / "skills" / "cd-test-architecture" / "SKILL.md"
TEST_EVALUATION = PLUGIN_ROOT / "docs" / "test-evaluation.md"
SESSION_REVIEW = PLUGIN_ROOT / "skills" / "session-review" / "SKILL.md"
DOCKER_IMAGE_AUDIT = PLUGIN_ROOT / "skills" / "docker-image-audit" / "SKILL.md"


def _cd_test_architecture_text() -> str:
    return CD_TEST_ARCHITECTURE.read_text()


def _test_evaluation_text() -> str:
    return TEST_EVALUATION.read_text()


def _session_review_text() -> str:
    return SESSION_REVIEW.read_text()


def _docker_image_audit_text() -> str:
    return DOCKER_IMAGE_AUDIT.read_text()


# --- cd-test-architecture/SKILL.md ------------------------------------------


def test_cd_test_architecture_names_step_2b_at_the_out_of_repo_check():
    text = _cd_test_architecture_text()
    assert (
        "see Step 2b — locate and harvest out-of-repo tests). Do not conclude"
        in text
    )


def test_cd_test_architecture_names_step_1_at_the_behavior_inventory_mapping():
    text = _cd_test_architecture_text()
    assert "from Step 1 (inventory the application's components)." in text


def test_cd_test_architecture_names_step_2b_at_the_source_material_flag():
    text = _cd_test_architecture_text()
    assert (
        "as the *source material* (Step 2b — locate and harvest out-of-repo tests), "
        "not the destination" in text
    )


def test_cd_test_architecture_names_step_2b_at_the_migration_path_intro():
    text = _cd_test_architecture_text()
    assert (
        "out-of-repo (Step 2b — locate and harvest out-of-repo tests), the harvested"
        in text
    )


def test_cd_test_architecture_has_no_bare_step_2b_back_reference_left():
    text = _cd_test_architecture_text()
    assert "(Step 2b)" not in text


def test_cd_test_architecture_step_1_and_2b_headings_are_unchanged():
    text = _cd_test_architecture_text()
    assert "### 1. Inventory the application's components" in text
    assert "### 2b. Locate and harvest out-of-repo tests" in text


# --- docs/test-evaluation.md -------------------------------------------------


def test_test_evaluation_names_step_2b_at_the_sparse_tests_check():
    text = _test_evaluation_text()
    assert (
        "see Step 2b (locate and harvest out-of-repo tests) before concluding."
        in text
    )


def test_test_evaluation_names_step_2b_at_the_behavior_inventory_intro():
    text = _test_evaluation_text()
    assert (
        "as a behavior inventory (Step 2b — locate and harvest out-of-repo tests) "
        "and builds the migration path" in text
    )


def test_test_evaluation_names_the_cross_skill_step_3_in_the_farley_score_row():
    text = _test_evaluation_text()
    assert (
        "called by `/test-design` Step 3 (Score the in-scope tests via Farley Score)"
        in text
    )


def test_test_evaluation_has_no_bare_step_2b_back_reference_left():
    text = _test_evaluation_text()
    assert "(Step 2b)" not in text
    assert "Step 2b before concluding" not in text


def test_test_evaluation_has_no_bare_cross_skill_step_3_reference_left():
    text = _test_evaluation_text()
    assert "`/test-design` Step 3 |" not in text


def test_test_evaluation_step_2b_heading_is_unchanged():
    text = _test_evaluation_text()
    assert "### Step 2b: Locate and harvest out-of-repo tests" in text


# --- session-review/SKILL.md --------------------------------------------------


def test_session_review_corrects_raw_log_tier_step_number_at_orchestrator_constraints():
    text = _session_review_text()
    assert (
        "the gated raw-log tier (Step 3b — the raw-log semantic tier): even there"
        in text
    )


def test_session_review_corrects_telemetry_sync_step_number_at_extract():
    text = _session_review_text()
    assert (
        "**If a telemetry repo synced in Step 1 (cross-machine telemetry sync)**, "
        "also build the cross-machine rollup" in text
    )


def test_session_review_names_step_3_at_the_escalation_lever_handoff():
    text = _session_review_text()
    assert "set the hand-off in Step 3 (Analyze, digest-only)." in text


def test_session_review_corrects_telemetry_sync_step_number_at_raw_log_tier():
    text = _session_review_text()
    assert (
        "the `$CLONE/digests` from Step 1 (cross-machine telemetry sync)); "
        "if no telemetry repo synced" in text
    )


def test_session_review_corrects_raw_log_tier_step_number_at_methodology_lens():
    text = _session_review_text()
    assert (
        "from Step 3b — the raw-log semantic tier — only) observes the "
        "*operator's own habits*" in text
    )


def test_session_review_has_no_wrong_step_2b_for_raw_log_tier_left():
    text = _session_review_text()
    assert "(Step 2b)" not in text
    assert "from Step 2b only" not in text


def test_session_review_has_no_wrong_step_0_for_telemetry_sync_left():
    text = _session_review_text()
    assert "synced in Step 0" not in text
    assert "digests` from Step 0" not in text


def test_session_review_has_no_bare_step_3_at_escalation_lever_left():
    text = _session_review_text()
    assert "hand-off in Step 3." not in text


def test_session_review_step_headings_are_unchanged():
    text = _session_review_text()
    assert "### 0. Queued Findings — surface pending-review queue before fresh analysis" in text
    assert "### 1. Cross-machine Telemetry — validate config, then sync (#178)" in text
    assert "### 3. Analyze (digest-only)" in text
    assert "### 3b. Raw-log semantic tier — only the worst sessions (#214, Delta A/B)" in text
