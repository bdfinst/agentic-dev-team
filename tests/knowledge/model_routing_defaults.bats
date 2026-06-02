#!/usr/bin/env bats
# Tests for plugins/dev-team/knowledge/model-routing.json — the
# single source of truth for tier → snapshot resolution defaults.
#
# AC1 (precondition) and AC2: the routing.json file is the ONLY in-tree
# place that ships a pinned snapshot ID. Every dispatch flows through it.

ROUTING_JSON="$BATS_TEST_DIRNAME/../../plugins/dev-team/knowledge/model-routing.json"

@test "model-routing.json exists" {
  [ -f "$ROUTING_JSON" ]
}

@test "model-routing.json is valid JSON" {
  run jq -e . "$ROUTING_JSON"
  [ "$status" -eq 0 ]
}

@test "model-routing.json contains exactly the three tier keys" {
  run jq -r 'keys | sort | join(",")' "$ROUTING_JSON"
  [ "$status" -eq 0 ]
  [ "$output" = "haiku,opus,sonnet" ]
}

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

@test "no tier resolves to null" {
  for tier in haiku sonnet opus; do
    run jq -e --arg t "$tier" '.[$t] != null and (.[$t] | type) == "string"' "$ROUTING_JSON"
    [ "$status" -eq 0 ]
  done
}
