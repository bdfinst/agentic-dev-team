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

# ---------------------------------------------------------------------------
# Slice 2 — /build's step-done instructions no longer tick the AC mirror
# ---------------------------------------------------------------------------

@test "526-2.1a: /build SKILL.md no longer references 'Build Progress `### Acceptance Criteria`'" {
  count=$(grep -c 'Build Progress \`### Acceptance Criteria\`' "$BUILD_SKILL" || true)
  [ "$count" -eq 0 ]
}

@test "526-2.1b: /build SKILL.md still contains the slice/step tick instructions (surrounding text preserved)" {
  # Anchor grep — the sub-bullet that ticks Step N.M checkboxes stays.
  grep -q 'Change \`- \[ \] Step N.M' "$BUILD_SKILL"
  # And the parent-slice tick.
  grep -q 'check off the parent \`- \[ \] Slice N' "$BUILD_SKILL"
}

@test "526-2.1c: /build SKILL.md still contains the pre-implementation 'Verify acceptance criteria (gate)' step" {
  # That's Step 3, AC-quality review — not the removed mirror-tick.
  grep -q 'Verify acceptance criteria (gate)' "$BUILD_SKILL"
}

# ---------------------------------------------------------------------------
# Slice 3 — belt-and-suspenders: the #525 guardian inner-skip is preserved
# so legacy plans (that still carry the AC mirror) don't false-positive.
# ---------------------------------------------------------------------------

@test "526-3.1a: full progress_guardian bats suite from #525 still passes end-to-end" {
  # Runs the guardian's own regression suite. If either the removal of the
  # /build AC-tick or any other post-#525 change accidentally regresses the
  # guardian, this fails loudly with which of the 22 tests broke.
  run bats --tap "$GUARDIAN_TESTS"
  [ "$status" -eq 0 ]
  ok_count=$(echo "$output" | grep -c '^ok ' || true)
  [ "$ok_count" -ge 22 ]
}

@test "526-3.1b: guardian's parse_plan still carries the in_acceptance inner-skip state" {
  # Belt-and-suspenders — legacy plans on branches that still carry the AC
  # mirror rely on this skip. Removing it would silently regress every
  # such branch's pre-PR gate.
  grep -q 'in_acceptance' "$GUARDIAN"
}

@test "526-3.1c: guardian's parse_plan still checks for '### Acceptance Criteria' as the skip trigger" {
  # The other half of the inner-skip pair.
  grep -q '### Acceptance Criteria' "$GUARDIAN"
}
