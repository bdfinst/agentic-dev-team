#!/usr/bin/env bats
# Doc-shape contract for the LOW_VALUE gap classification (epic #443, issue #431).
#
# LOW_VALUE is the third gap class alongside NO_REFACTOR / REFACTOR_REQUIRED:
# technically-feasible findings that deliver no signal, plus existing low-value
# tests that should be removed because a higher-layer test already covers the
# same low-complexity code. These tests guard the doc-only invariants across the
# four artifacts the slice touches.

PLUGIN="$BATS_TEST_DIRNAME/../../plugins/dev-team"
TEST_HEALTH="$PLUGIN/skills/test-health/SKILL.md"
SPECS="$PLUGIN/skills/specs/SKILL.md"
PLAN="$PLUGIN/skills/plan/SKILL.md"
SMELL="$PLUGIN/agents/test-smell-review.md"

# --- test-health: LOW_VALUE column + Recommended removals table -------------

@test "test-health: gap table documents a LOW_VALUE class" {
  run grep -q 'LOW_VALUE' "$TEST_HEALTH"
  [ "$status" -eq 0 ]
}

@test "test-health: has a Recommended removals table" {
  run grep -qi 'Recommended removals' "$TEST_HEALTH"
  [ "$status" -eq 0 ]
}

@test "test-health: Recommended removals names a covering test and rationale" {
  # The table must carry the covering test + one-line rationale columns so a
  # reader knows why each removal is safe.
  run grep -Eqi 'covering test' "$TEST_HEALTH"
  [ "$status" -eq 0 ]
}

@test "test-health: LOW_VALUE definition names the three criteria" {
  # No branching logic + no observable outcome + coverage already provided.
  grep -qi 'no branch' "$TEST_HEALTH"
  grep -qi 'observable' "$TEST_HEALTH"
  grep -Eqi 'higher.(layer|level)' "$TEST_HEALTH"
}

# --- specs: LOW_VALUE is skip, not defer ------------------------------------

@test "specs: documents LOW_VALUE classification" {
  run grep -q 'LOW_VALUE' "$SPECS"
  [ "$status" -eq 0 ]
}

@test "specs: LOW_VALUE is skip not defer" {
  # The instruction must say skip (not defer) so low-value work never lingers
  # as deferred backlog.
  run grep -Eqi 'skip[^.]*not[^.]*defer|skip, not defer' "$SPECS"
  [ "$status" -eq 0 ]
}

# --- plan: LOW_VALUE filtered into a Skipped section; gate rejects ----------

@test "plan: has a Skipped (low value) section" {
  run grep -Eqi 'Skipped \(low value\)|Skipped \(low.value\)' "$PLAN"
  [ "$status" -eq 0 ]
}

@test "plan: gate rejects any slice classified LOW_VALUE" {
  run grep -q 'LOW_VALUE' "$PLAN"
  [ "$status" -eq 0 ]
  # And the rejection must be explicit.
  run grep -Eqi 'reject' "$PLAN"
  [ "$status" -eq 0 ]
}

# --- test-smell-review: redundant low-level test as a named warning smell ---

@test "test-smell-review: detects redundant low-level tests as a named smell" {
  run grep -Eqi 'Redundant Low-Level Test' "$SMELL"
  [ "$status" -eq 0 ]
}

@test "test-smell-review: redundant low-level smell is severity warning with removal action" {
  grep -Eqi 'Redundant Low-Level Test' "$SMELL"
  grep -Eqi 'warning' "$SMELL"
  grep -Eqi 'removal|remove' "$SMELL"
}
