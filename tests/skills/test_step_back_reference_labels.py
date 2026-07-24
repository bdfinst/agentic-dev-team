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
