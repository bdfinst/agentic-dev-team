#!/usr/bin/env bats

BUILD_SKILL="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/build/SKILL.md"
PR_SKILL="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/pr/SKILL.md"

@test "build skill references progress_guardian.py" {
  grep -q "scripts/progress_guardian.py" "$BUILD_SKILL"
}

@test "build skill does not dispatch progress-guardian agent" {
  # should not contain dispatch patterns like "progress-guardian agent" or "dispatch progress-guardian"
  ! grep -qE "(dispatch|Agent:)\s+progress-guardian" "$BUILD_SKILL"
}

@test "pr skill references progress_guardian.py --pre-pr" {
  grep -q "scripts/progress_guardian.py --pre-pr" "$PR_SKILL"
}

@test "pr skill does not dispatch progress-guardian agent" {
  ! grep -qE "(dispatch|Agent:)\s+progress-guardian" "$PR_SKILL"
}
