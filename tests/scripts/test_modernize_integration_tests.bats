#!/usr/bin/env bats

SKILL="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/test-modernize/SKILL.md"

@test "test-modernize skill references test_modernization_review.py" {
  grep -q "scripts/test_modernization_review.py" "$SKILL"
}

@test "test-modernize skill references --repo and --phase flags" {
  grep -q "test_modernization_review.py" "$SKILL" && \
  grep -E "\-\-repo|\-\-phase" "$SKILL"
}

@test "test-modernize skill does not dispatch test-modernization-review agent" {
  ! grep -qE "(dispatch|Agent:)\s+test-modernization-review" "$SKILL"
}
