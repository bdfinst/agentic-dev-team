"""Regression coverage for issue #526: the /plan template no longer renders
an `### Acceptance Criteria` mirror inside `## Build Progress`, and /build
no longer tries to tick items in that (removed) subsection. Ships with a
belt-and-suspenders assertion that the #525 guardian inner-skip logic is
still present in scripts/progress_guardian.py so legacy plans still work.

Ported from tests/repo/plan-template-tests.bats (#673).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PLAN_SKILL = REPO_ROOT / "plugins" / "dev-team" / "skills" / "plan" / "SKILL.md"
BUILD_SKILL = REPO_ROOT / "plugins" / "dev-team" / "skills" / "build" / "SKILL.md"
GUARDIAN = REPO_ROOT / "scripts" / "progress_guardian.py"
GUARDIAN_TESTS = REPO_ROOT / "tests" / "scripts" / "progress_guardian_tests.bats"

# ---------------------------------------------------------------------------
# Slice 1 - /plan template + Step 4 prose
# ---------------------------------------------------------------------------


def test_526_1_1a_plan_skill_no_longer_has_acceptance_criteria_subheading() -> None:
    text = PLAN_SKILL.read_text()
    count = len(re.findall(r"^### Acceptance Criteria$", text, re.MULTILINE))
    assert count == 0


def test_526_1_1b_plan_skill_still_declares_top_level_acceptance_criteria_heading() -> (
    None
):
    text = PLAN_SKILL.read_text()
    count = len(re.findall(r"^## Acceptance Criteria$", text, re.MULTILINE))
    assert count >= 1


def test_526_1_1c_plan_step_4_no_longer_instructs_copying_ac_mirror() -> None:
    text = PLAN_SKILL.read_text()
    count = text.count("criteria from `## Acceptance Criteria`")
    assert count == 0


# ---------------------------------------------------------------------------
# Slice 2 - /build's step-done instructions no longer tick the AC mirror
# ---------------------------------------------------------------------------


def test_526_2_1a_build_skill_no_longer_references_build_progress_ac_mirror() -> None:
    text = BUILD_SKILL.read_text()
    count = text.count("Build Progress `### Acceptance Criteria`")
    assert count == 0


def test_526_2_1b_build_skill_still_contains_slice_step_tick_instructions() -> None:
    # Anchor via fixed-string match - the sub-bullet that ticks Step N.M
    # checkboxes stays.
    text = BUILD_SKILL.read_text()
    assert "Change `- [ ] Step N.M" in text
    # And the parent-slice tick.
    assert "check off the parent `- [ ] Slice N" in text


def test_526_2_1c_build_skill_still_contains_verify_acceptance_criteria_step() -> None:
    # That's Step 3, AC-quality review - not the removed mirror-tick.
    assert "Verify acceptance criteria (gate)" in BUILD_SKILL.read_text()


# ---------------------------------------------------------------------------
# Slice 3 - belt-and-suspenders: the #525 guardian inner-skip is preserved so
# legacy plans (that still carry the AC mirror) don't false-positive.
# ---------------------------------------------------------------------------


def test_526_3_1a_full_progress_guardian_bats_suite_still_passes_end_to_end() -> None:
    # Runs the guardian's own regression suite. If either the removal of the
    # /build AC-tick or any other post-#525 change accidentally regresses the
    # guardian, this fails loudly with which of the 22 tests broke.
    if shutil.which("bats") is None:
        pytest.skip("bats not installed")
    result = subprocess.run(
        ["bats", "--tap", str(GUARDIAN_TESTS)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    ok_count = len(re.findall(r"^ok ", result.stdout, re.MULTILINE))
    assert ok_count >= 22


def test_526_3_1b_guardian_parse_plan_carries_in_acceptance_inner_skip_state() -> None:
    # Belt-and-suspenders - legacy plans on branches that still carry the AC
    # mirror rely on this skip. Removing it would silently regress every such
    # branch's pre-PR gate.
    assert "in_acceptance" in GUARDIAN.read_text()


def test_526_3_1c_guardian_parse_plan_checks_for_acceptance_criteria_skip_trigger() -> (
    None
):
    # The other half of the inner-skip pair.
    assert "### Acceptance Criteria" in GUARDIAN.read_text()
