"""Regression coverage for issue #526: the /plan template no longer renders
an `### Acceptance Criteria` mirror inside `## Build Progress`, and /build
no longer tries to tick items in that (removed) subsection. Ships with a
belt-and-suspenders assertion that the #525 guardian inner-skip logic is
still present so legacy plans still work. Since #2275 the guardian reads the
feature record and the skip lives in plugins/dev-team/scripts/lib/plan_record_parse.py.

Ported from tests/repo/plan-template-tests.bats (#673).
"""

from __future__ import annotations

import importlib.util
import re

from _repo_root import REPO_ROOT

PLAN_SKILL = REPO_ROOT / "plugins" / "dev-team" / "skills" / "plan" / "SKILL.md"
# The plan-file template (goal/AC/slices/... structure) was later extracted
# from SKILL.md's body into this reference file (token-efficiency cleanup).
PLAN_TEMPLATE = (
    REPO_ROOT
    / "plugins"
    / "dev-team"
    / "skills"
    / "plan"
    / "references"
    / "plan-template.md"
)
BUILD_SKILL = REPO_ROOT / "plugins" / "dev-team" / "skills" / "build" / "SKILL.md"
# Since #2275 the guardian reads the feature record; the Build Progress parse
# (and the Acceptance Criteria mirror skip) lives here.
PLAN_RECORD_PARSE = (
    REPO_ROOT / "plugins" / "dev-team" / "scripts" / "lib" / "plan_record_parse.py"
)

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
    # The heading lives in the plan-file template, extracted from SKILL.md's
    # body into references/plan-template.md (token-efficiency cleanup).
    text = PLAN_SKILL.read_text() + "\n" + PLAN_TEMPLATE.read_text()
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


def test_526_3_1b_build_progress_parse_skips_the_acceptance_criteria_mirror() -> None:
    # Belt-and-suspenders - legacy plans on branches that still carry the AC
    # mirror rely on this skip. Removing it would silently regress every such
    # branch's pre-PR gate. Behavioral: the mirror lines are not items, the
    # real slice after the mirror is.
    spec = importlib.util.spec_from_file_location(
        "plan_record_parse_under_test", PLAN_RECORD_PARSE
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    plan = (
        "## Build Progress\n\n"
        "### Acceptance Criteria\n- [x] AC1 mirrored\n\n"
        "### Slices\n- [ ] Slice 1: real work\n"
    )
    headers = [i["header"] for i in module.parse_build_progress(plan)["items"]]

    assert headers == ["Slice 1: real work"]


def test_526_3_1c_build_progress_parse_checks_for_acceptance_criteria_skip_trigger() -> (
    None
):
    # The other half of the inner-skip pair.
    assert "### Acceptance Criteria" in PLAN_RECORD_PARSE.read_text()
