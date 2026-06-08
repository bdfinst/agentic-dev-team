#!/usr/bin/env bats
# #225 — issue-deps.sh derives per-slice sibling dependency sets from the plan
# DAG (via plan-waves.sh), not file order. Model-free.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
DEPS="$REPO_ROOT/scripts/issue-deps.sh"
FIX="$REPO_ROOT/tests/fixtures/plans"

@test "diamond: each slice maps to its direct predecessors" {
  run "$DEPS" "$FIX/diamond.md"
  [ "$status" -eq 0 ]
  [ "$(echo "$output" | jq -c '.A')" = '[]' ]
  [ "$(echo "$output" | jq -c '.B')" = '["A"]' ]
  [ "$(echo "$output" | jq -c '.D')" = '["B","C"]' ]
}

@test "single-slice plan yields one slice with no dependency" {
  TMP="$(mktemp)"; printf '### Slice 1: only\n**Depends-on:** none\n' > "$TMP"
  run "$DEPS" "$TMP"
  rm -f "$TMP"
  [ "$status" -eq 0 ]
  [ "$(echo "$output" | jq -c '.["1"]')" = '[]' ]
  [ "$(echo "$output" | jq -c 'length')" = '1' ]
}

@test "links follow the DAG, not file order (dep listed after dependent)" {
  run "$DEPS" "$FIX/dag-order.md"
  [ "$status" -eq 0 ]
  # B is listed first but depends on A (listed second)
  [ "$(echo "$output" | jq -c '.B')" = '["A"]' ]
  # C is listed last and independent — no dependency on the earlier slices
  [ "$(echo "$output" | jq -c '.C')" = '[]' ]
}

@test "an invalid plan (cycle) propagates non-zero" {
  run "$DEPS" "$FIX/cycle.md"
  [ "$status" -ne 0 ]
}

@test "missing file argument exits non-zero with usage" {
  run "$DEPS"
  [ "$status" -ne 0 ]
  [[ "$output" == *"usage:"* ]]
}
