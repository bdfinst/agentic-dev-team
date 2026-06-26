#!/usr/bin/env bats
# Tests for hooks/lib/model-resolve.sh — pre-dispatch effort band → model
# resolver. Pure shell + jq. Maps a band (low|medium|high) to a model via the
# shipped default map in knowledge/model-routing.json, or — when present and
# valid — via an ordered ladder at .claude/model-ladder.json using
# index = round_half_up(weight·(N−1)). Legacy tiers (haiku|sonnet|opus) are
# accepted for the migration window and normalized to bands.
#
# Env vars (test-only injection seams; documented as such in the helper):
#   MODEL_ROUTING_JSON   defaults to <plugin>/knowledge/model-routing.json
#   MODEL_LADDER_JSON    defaults to .claude/model-ladder.json
#
# Exit codes:
#   0 — resolved successfully
#   2 — unknown band/tier (caller error)
#   4 — knowledge/model-routing.json missing

RESOLVER="$BATS_TEST_DIRNAME/../../plugins/dev-team/hooks/lib/model-resolve.sh"

setup() {
  BATS_TMPDIR_CASE="$(mktemp -d)"
  # Fixture routing.json mirrors the plugin defaults so the test is
  # decoupled from drift in the shipped file.
  cat > "$BATS_TMPDIR_CASE/routing.json" <<'EOF'
{
  "low": "claude-haiku-4-5-20251001",
  "medium": "claude-sonnet-4-6",
  "high": "claude-opus-4-8",
  "haiku": "claude-haiku-4-5-20251001",
  "sonnet": "claude-sonnet-4-6",
  "opus": "claude-opus-4-8",
  "rounding": "round_half_up"
}
EOF
  export MODEL_ROUTING_JSON="$BATS_TMPDIR_CASE/routing.json"
  export MODEL_LADDER_JSON="$BATS_TMPDIR_CASE/model-ladder.json"  # not created → optional
}

teardown() {
  rm -rf "$BATS_TMPDIR_CASE"
  unset MODEL_ROUTING_JSON MODEL_LADDER_JSON
}

# ---------------------------------------------------------------------------
# Default map (no ladder) — migration safety
# ---------------------------------------------------------------------------

@test "resolver: low band resolves to the haiku default snapshot" {
  run bash "$RESOLVER" low
  [ "$status" -eq 0 ]
  [ "$output" = "claude-haiku-4-5-20251001" ]
}

@test "resolver: medium band resolves to the sonnet default snapshot" {
  run bash "$RESOLVER" medium
  [ "$status" -eq 0 ]
  [ "$output" = "claude-sonnet-4-6" ]
}

@test "resolver: high band resolves to the opus default snapshot" {
  run bash "$RESOLVER" high
  [ "$status" -eq 0 ]
  [ "$output" = "claude-opus-4-8" ]
}

@test "resolver: no-ladder bands equal the pre-migration tier snapshots" {
  [ "$(bash "$RESOLVER" low)" = "claude-haiku-4-5-20251001" ]
  [ "$(bash "$RESOLVER" medium)" = "claude-sonnet-4-6" ]
  [ "$(bash "$RESOLVER" high)" = "claude-opus-4-8" ]
}

# ---------------------------------------------------------------------------
# Legacy tier acceptance (migration window) — tier → band normalization
# ---------------------------------------------------------------------------

@test "resolver: legacy haiku tier normalizes to low" {
  run bash "$RESOLVER" haiku
  [ "$status" -eq 0 ]
  [ "$output" = "claude-haiku-4-5-20251001" ]
}

@test "resolver: legacy sonnet tier normalizes to medium" {
  run bash "$RESOLVER" sonnet
  [ "$status" -eq 0 ]
  [ "$output" = "claude-sonnet-4-6" ]
}

@test "resolver: legacy opus tier normalizes to high" {
  run bash "$RESOLVER" opus
  [ "$status" -eq 0 ]
  [ "$output" = "claude-opus-4-8" ]
}

# ---------------------------------------------------------------------------
# Caller errors
# ---------------------------------------------------------------------------

@test "resolver: unknown band exits 2 with actionable stderr" {
  run bash -c "bash '$RESOLVER' frontier 2>&1 1>/dev/null"
  [ "$status" -eq 2 ]
  [[ "$output" == *"Unknown"* ]]
  [[ "$output" == *"low"* ]]
  [[ "$output" == *"medium"* ]]
  [[ "$output" == *"high"* ]]
}

@test "resolver: missing band argument exits 2 with usage message" {
  run bash "$RESOLVER"
  [ "$status" -eq 2 ]
}

@test "resolver: --caller is accepted and ignored" {
  run bash "$RESOLVER" medium --caller naming-review
  [ "$status" -eq 0 ]
  [ "$output" = "claude-sonnet-4-6" ]
}

# ---------------------------------------------------------------------------
# Ladder path — index = round_half_up(weight·(N−1))
# ---------------------------------------------------------------------------

@test "ladder N=3 [haiku,sonnet,opus] reproduces the default map" {
  cat > "$MODEL_LADDER_JSON" <<'EOF'
["claude-haiku-4-5-20251001", "claude-sonnet-4-6", "claude-opus-4-8"]
EOF
  [ "$(bash "$RESOLVER" low)" = "claude-haiku-4-5-20251001" ]
  [ "$(bash "$RESOLVER" medium)" = "claude-sonnet-4-6" ]
  [ "$(bash "$RESOLVER" high)" = "claude-opus-4-8" ]
}

@test "ladder N=2 [sonnet,opus]: low→sonnet, medium→opus, high→opus" {
  cat > "$MODEL_LADDER_JSON" <<'EOF'
["claude-sonnet-4-6", "claude-opus-4-8"]
EOF
  [ "$(bash "$RESOLVER" low)" = "claude-sonnet-4-6" ]
  [ "$(bash "$RESOLVER" medium)" = "claude-opus-4-8" ]
  [ "$(bash "$RESOLVER" high)" = "claude-opus-4-8" ]
}

@test "ladder N=1 [sonnet]: every band collapses to the single model" {
  cat > "$MODEL_LADDER_JSON" <<'EOF'
["claude-sonnet-4-6"]
EOF
  [ "$(bash "$RESOLVER" low)" = "claude-sonnet-4-6" ]
  [ "$(bash "$RESOLVER" medium)" = "claude-sonnet-4-6" ]
  [ "$(bash "$RESOLVER" high)" = "claude-sonnet-4-6" ]
}

@test "ladder N=4 [haiku,sonnet,opus,max]: medium lands on index 2 (round half up)" {
  cat > "$MODEL_LADDER_JSON" <<'EOF'
["claude-haiku-4-5-20251001", "claude-sonnet-4-6", "claude-opus-4-8", "claude-opusmax-9"]
EOF
  [ "$(bash "$RESOLVER" low)" = "claude-haiku-4-5-20251001" ]
  [ "$(bash "$RESOLVER" medium)" = "claude-opus-4-8" ]
  [ "$(bash "$RESOLVER" high)" = "claude-opusmax-9" ]
}

@test "ladder feeds legacy tiers too: sonnet (→medium) with N=2 → opus" {
  cat > "$MODEL_LADDER_JSON" <<'EOF'
["claude-sonnet-4-6", "claude-opus-4-8"]
EOF
  [ "$(bash "$RESOLVER" sonnet)" = "claude-opus-4-8" ]
}

# ---------------------------------------------------------------------------
# Malformed / degenerate ladder → degrade to the default map (never abort)
# ---------------------------------------------------------------------------

@test "malformed ladder (invalid JSON) degrades to the default map" {
  echo '[not valid json' > "$MODEL_LADDER_JSON"
  run bash "$RESOLVER" medium
  [ "$status" -eq 0 ]
  [ "$output" = "claude-sonnet-4-6" ]
}

@test "ladder that is an object (not an array) degrades to the default map" {
  echo '{"low": "x"}' > "$MODEL_LADDER_JSON"
  run bash "$RESOLVER" high
  [ "$status" -eq 0 ]
  [ "$output" = "claude-opus-4-8" ]
}

@test "empty ladder array degrades to the default map" {
  echo '[]' > "$MODEL_LADDER_JSON"
  run bash "$RESOLVER" low
  [ "$status" -eq 0 ]
  [ "$output" = "claude-haiku-4-5-20251001" ]
}

@test "ladder with non-string elements degrades to the default map" {
  echo '[1, 2, 3]' > "$MODEL_LADDER_JSON"
  run bash "$RESOLVER" medium
  [ "$status" -eq 0 ]
  [ "$output" = "claude-sonnet-4-6" ]
}

# ---------------------------------------------------------------------------
# Missing routing.json (the one surviving deny-relevant exit)
# ---------------------------------------------------------------------------

@test "missing routing.json exits 4 with remediation" {
  export MODEL_ROUTING_JSON="$BATS_TMPDIR_CASE/does-not-exist.json"
  run bash -c "bash '$RESOLVER' low 2>&1 1>/dev/null"
  [ "$status" -eq 4 ]
  [[ "$output" == *"Model routing file missing:"* ]]
  [[ "$output" == *"git checkout knowledge/model-routing.json"* ]]
}

# ---------------------------------------------------------------------------
# --dump-map flag
# ---------------------------------------------------------------------------

@test "--dump-map prints the three bands with their default snapshots" {
  run bash "$RESOLVER" --dump-map
  [ "$status" -eq 0 ]
  [[ "$output" == *"low"* ]]
  [[ "$output" == *"medium"* ]]
  [[ "$output" == *"high"* ]]
  [[ "$output" == *"claude-haiku-4-5-20251001"* ]]
  [[ "$output" == *"claude-sonnet-4-6"* ]]
  [[ "$output" == *"claude-opus-4-8"* ]]
}

@test "--dump-map reflects the ladder when present" {
  cat > "$MODEL_LADDER_JSON" <<'EOF'
["claude-sonnet-4-6", "claude-opus-4-8"]
EOF
  run bash "$RESOLVER" --dump-map
  [ "$status" -eq 0 ]
  # low now resolves to the sonnet snapshot (bottom of the ladder)
  [[ "$output" == *"claude-sonnet-4-6"* ]]
  # high resolves to opus (top)
  [[ "$output" == *"claude-opus-4-8"* ]]
}

@test "--dump-map writes no files" {
  bash "$RESOLVER" --dump-map >/dev/null
  [ ! -e "$MODEL_LADDER_JSON" ]
}
