#!/usr/bin/env bats
# plan-waves.sh (#222) — parallel build-wave computation from a plan's slice DAG.
# Deterministic and model-free; covers the slice-1 Gherkin scenarios.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
WAVES="$REPO_ROOT/plugins/dev-team/scripts/plan-waves.sh"
FIX="$REPO_ROOT/tests/fixtures/plans"

@test "diamond dependencies layer into waves (A -> {B,C} -> D)" {
  run "$WAVES" "$FIX/diamond.md"
  [ "$status" -eq 0 ]
  [ "$(echo "$output" | jq -c '.waves')" = '[["A"],["B","C"],["D"]]' ]
}

@test "a plan with no dependencies is one wave" {
  run "$WAVES" "$FIX/nodeps.md"
  [ "$status" -eq 0 ]
  [ "$(echo "$output" | jq -c '.waves')" = '[["A","B","C"]]' ]
}

@test "linear plan layers in order; step-level Files do not pollute slice Files" {
  run "$WAVES" "$FIX/linear.md"
  [ "$status" -eq 0 ]
  [ "$(echo "$output" | jq -c '.waves')" = '[["1"],["2"]]' ]
  # slice 1's surface is its slice-level Files only, not the #### step's Files
  [ "$(echo "$output" | jq -c '.slices."1".files')" = '["one.ts"]' ]
}

@test "same-wave file collision is surfaced" {
  run "$WAVES" "$FIX/collision.md"
  [ "$status" -eq 0 ]
  [ "$(echo "$output" | jq -r '.collisions[0].file')" = "shared.ts" ]
  [ "$(echo "$output" | jq -c '.collisions[0].slices')" = '["B","C"]' ]
}

@test "a dependency cycle is rejected, naming the involved slices" {
  run "$WAVES" "$FIX/cycle.md"
  [ "$status" -ne 0 ]
  [[ "$output" == *"cycle"* ]]
  [[ "$output" == *"A"* && "$output" == *"B"* ]]
}

@test "a missing Depends-on field is rejected with the 'Depends-on: none' remedy" {
  run "$WAVES" "$FIX/missing.md"
  [ "$status" -ne 0 ]
  [[ "$output" == *"missing its Depends-on"* ]]
  [[ "$output" == *"Depends-on: none"* ]]
}

@test "an unknown dependency reference is rejected" {
  run "$WAVES" "$FIX/unknown.md"
  [ "$status" -ne 0 ]
  [[ "$output" == *"unknown slice"* ]]
  [[ "$output" == *"Z"* ]]
}

@test "missing plan file argument exits non-zero with usage" {
  run "$WAVES"
  [ "$status" -ne 0 ]
  [[ "$output" == *"usage:"* ]]
}
