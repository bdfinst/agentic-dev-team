#!/usr/bin/env bats
# Tests for plugins/dev-team/knowledge/model-routing.json — the
# single source of truth for effort band → snapshot resolution defaults.
#
# AC0 (migration safety): each band default must equal the legacy tier it
# replaces, snapshot-for-snapshot (low→haiku, medium→sonnet, high→opus).
# AC1 (precondition) and AC2: the routing.json file is the ONLY in-tree
# place that ships a pinned snapshot ID, and it pins the ladder rounding
# convention. Every dispatch flows through it. Legacy tier keys are retained
# for the migration window (AC3) so the unchanged resolver keeps resolving.

ROUTING_JSON="$BATS_TEST_DIRNAME/../../plugins/dev-team/knowledge/model-routing.json"

@test "model-routing.json exists" {
  [ -f "$ROUTING_JSON" ]
}

@test "model-routing.json is valid JSON" {
  run jq -e . "$ROUTING_JSON"
  [ "$status" -eq 0 ]
}

@test "model-routing.json contains the three effort bands and the legacy tiers" {
  run jq -r 'keys | sort | join(",")' "$ROUTING_JSON"
  [ "$status" -eq 0 ]
  [ "$output" = "haiku,high,low,medium,opus,rounding,sonnet" ]
}

# --- Effort band defaults (the post-migration vocabulary) -------------------

@test "low band maps to the documented haiku snapshot" {
  run jq -r '.low' "$ROUTING_JSON"
  [ "$status" -eq 0 ]
  [ "$output" = "claude-haiku-4-5-20251001" ]
}

@test "medium band maps to the unpinned canonical sonnet ID" {
  run jq -r '.medium' "$ROUTING_JSON"
  [ "$status" -eq 0 ]
  [ "$output" = "claude-sonnet-4-6" ]
}

@test "high band maps to the unpinned canonical opus ID" {
  run jq -r '.high' "$ROUTING_JSON"
  [ "$status" -eq 0 ]
  [ "$output" = "claude-opus-4-8" ]
}

# --- AC0: bands equal the legacy tiers they replace, snapshot-for-snapshot ---

@test "each band default equals its legacy tier snapshot (AC0 migration safety)" {
  run jq -e '.low == .haiku and .medium == .sonnet and .high == .opus' "$ROUTING_JSON"
  [ "$status" -eq 0 ]
}

# --- AC3: legacy tier keys retained for the migration window ----------------

@test "haiku tier maps to the documented snapshot" {
  run jq -r '.haiku' "$ROUTING_JSON"
  [ "$status" -eq 0 ]
  [ "$output" = "claude-haiku-4-5-20251001" ]
}

@test "sonnet tier maps to the unpinned canonical ID" {
  run jq -r '.sonnet' "$ROUTING_JSON"
  [ "$status" -eq 0 ]
  [ "$output" = "claude-sonnet-4-6" ]
}

@test "opus tier maps to the unpinned canonical ID" {
  run jq -r '.opus' "$ROUTING_JSON"
  [ "$status" -eq 0 ]
  [ "$output" = "claude-opus-4-8" ]
}

# --- AC2: ladder rounding convention is pinned -----------------------------

@test "rounding convention is pinned to round_half_up" {
  run jq -r '.rounding' "$ROUTING_JSON"
  [ "$status" -eq 0 ]
  [ "$output" = "round_half_up" ]
}

# --- No band or tier resolves to null --------------------------------------

@test "no band or tier resolves to null" {
  for key in low medium high haiku sonnet opus; do
    run jq -e --arg k "$key" '.[$k] != null and (.[$k] | type) == "string"' "$ROUTING_JSON"
    [ "$status" -eq 0 ]
  done
}
