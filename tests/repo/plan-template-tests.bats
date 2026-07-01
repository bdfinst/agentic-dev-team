#!/usr/bin/env bats
#
# Regression coverage for issue #526: the /plan template no longer renders
# an `### Acceptance Criteria` mirror inside `## Build Progress`, and /build
# no longer tries to tick items in that (removed) subsection. Ships with a
# belt-and-suspenders assertion that the #525 guardian inner-skip logic is
# still present in scripts/progress_guardian.py so legacy plans still work.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
PLAN_SKILL="$REPO_ROOT/plugins/dev-team/skills/plan/SKILL.md"
BUILD_SKILL="$REPO_ROOT/plugins/dev-team/skills/build/SKILL.md"
GUARDIAN="$REPO_ROOT/scripts/progress_guardian.py"
GUARDIAN_TESTS="$REPO_ROOT/tests/scripts/progress_guardian_tests.bats"

# ---------------------------------------------------------------------------
# Slice 1 — /plan template + Step 4 prose
# ---------------------------------------------------------------------------

@test "526-1.1a: /plan SKILL.md no longer contains an `### Acceptance Criteria` subheading" {
  count=$(grep -c '^### Acceptance Criteria$' "$PLAN_SKILL" || true)
  [ "$count" -eq 0 ]
}

@test "526-1.1b: /plan SKILL.md still declares a top-level `## Acceptance Criteria` heading" {
  run grep -c '^## Acceptance Criteria$' "$PLAN_SKILL"
  [ "$status" -eq 0 ]
  [ "$output" -ge 1 ]
}

@test "526-1.1c: /plan Step 4 prose no longer instructs copying 'criteria from ## Acceptance Criteria'" {
  count=$(grep -c 'criteria from \`## Acceptance Criteria\`' "$PLAN_SKILL" || true)
  [ "$count" -eq 0 ]
}
