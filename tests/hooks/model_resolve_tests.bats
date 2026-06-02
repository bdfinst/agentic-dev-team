#!/usr/bin/env bats
# Tests for hooks/lib/model-resolve.sh — pre-dispatch tier → snapshot
# resolver. Pure shell + jq. Reads knowledge/model-routing.json and an
# optional .claude/model-overrides.json; walks the alias chain; prints
# the resolved snapshot on stdout; appends JSONL bump events.
#
# Env vars (test-only injection seams; documented as such in the helper):
#   MODEL_ROUTING_JSON     defaults to <plugin>/knowledge/model-routing.json
#   MODEL_OVERRIDES_JSON   defaults to .claude/model-overrides.json
#   MODEL_BUMP_LOG         defaults to .claude/metrics/model-routing.log
#
# Exit codes:
#   0 — resolved successfully
#   2 — unknown tier (caller error)
#   3 — exhausted / cycle (resolver cannot satisfy request)
#   4 — knowledge/model-routing.json missing
#   5 — overrides file is not valid JSON

RESOLVER="$BATS_TEST_DIRNAME/../../plugins/dev-team/hooks/lib/model-resolve.sh"

setup() {
  BATS_TMPDIR_CASE="$(mktemp -d)"
  # Fixture routing.json mirrors the plugin defaults so the test is
  # decoupled from drift in the shipped file.
  cat > "$BATS_TMPDIR_CASE/routing.json" <<'EOF'
{
  "haiku": "claude-haiku-4-5-20251001",
  "sonnet": "claude-sonnet-4-6",
  "opus": "claude-opus-4-8"
}
EOF
  export MODEL_ROUTING_JSON="$BATS_TMPDIR_CASE/routing.json"
  export MODEL_OVERRIDES_JSON="$BATS_TMPDIR_CASE/overrides.json"  # not created → optional
  export MODEL_BUMP_LOG="$BATS_TMPDIR_CASE/metrics/model-routing.log"
}

teardown() {
  rm -rf "$BATS_TMPDIR_CASE"
  unset MODEL_ROUTING_JSON MODEL_OVERRIDES_JSON MODEL_BUMP_LOG
}

# ---------------------------------------------------------------------------
# Step 3 — happy path (no override)
# ---------------------------------------------------------------------------

@test "resolver: haiku resolves to its default snapshot" {
  run bash "$RESOLVER" haiku
  [ "$status" -eq 0 ]
  [ "$output" = "claude-haiku-4-5-20251001" ]
}

@test "resolver: sonnet resolves to its default snapshot" {
  run bash "$RESOLVER" sonnet
  [ "$status" -eq 0 ]
  [ "$output" = "claude-sonnet-4-6" ]
}

@test "resolver: opus resolves to its default snapshot" {
  run bash "$RESOLVER" opus
  [ "$status" -eq 0 ]
  [ "$output" = "claude-opus-4-8" ]
}

@test "resolver: unknown tier exits 2 with actionable stderr" {
  run bash -c "bash '$RESOLVER' gpt 2>&1 1>/dev/null"
  [ "$status" -eq 2 ]
  [[ "$output" == *"Unknown tier 'gpt'"* ]]
  [[ "$output" == *"haiku"* ]]
  [[ "$output" == *"sonnet"* ]]
  [[ "$output" == *"opus"* ]]
}

@test "resolver: happy path writes no files under .claude/metrics/" {
  bash "$RESOLVER" haiku >/dev/null
  [ ! -e "$MODEL_BUMP_LOG" ]
}

@test "resolver: missing tier argument exits 2 with usage message" {
  run bash "$RESOLVER"
  [ "$status" -eq 2 ]
}

# ---------------------------------------------------------------------------
# Step 4 — single-hop override + bump logging
# ---------------------------------------------------------------------------

@test "step4: override haiku→sonnet resolves to sonnet snapshot" {
  cat > "$MODEL_OVERRIDES_JSON" <<'EOF'
{ "tier_aliases": { "haiku": "sonnet" } }
EOF
  run bash "$RESOLVER" haiku --caller naming-review
  [ "$status" -eq 0 ]
  [ "$output" = "claude-sonnet-4-6" ]
}

@test "step4: override haiku→sonnet appends exactly one bump log line" {
  cat > "$MODEL_OVERRIDES_JSON" <<'EOF'
{ "tier_aliases": { "haiku": "sonnet" } }
EOF
  bash "$RESOLVER" haiku --caller naming-review >/dev/null
  [ -f "$MODEL_BUMP_LOG" ]
  local line_count
  line_count=$(wc -l < "$MODEL_BUMP_LOG" | tr -d ' ')
  [ "$line_count" = "1" ]
}

@test "step4: bump log line has the required JSONL shape" {
  cat > "$MODEL_OVERRIDES_JSON" <<'EOF'
{ "tier_aliases": { "haiku": "sonnet" } }
EOF
  bash "$RESOLVER" haiku --caller naming-review >/dev/null
  local line
  line=$(head -n 1 "$MODEL_BUMP_LOG")
  # Each required field via jq
  [ "$(echo "$line" | jq -r '.requested')" = "haiku" ]
  [ "$(echo "$line" | jq -r '.served')" = "sonnet" ]
  [ "$(echo "$line" | jq -r '.reason')" = "override" ]
  [ "$(echo "$line" | jq -r '.caller')" = "naming-review" ]
  # ts is ISO-8601 (rough shape check)
  local ts
  ts=$(echo "$line" | jq -r '.ts')
  [[ "$ts" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z?$ ]] || \
    [[ "$ts" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}[+-][0-9]{2}:?[0-9]{2}$ ]]
}

@test "step4: bump log directory is created on demand" {
  cat > "$MODEL_OVERRIDES_JSON" <<'EOF'
{ "tier_aliases": { "haiku": "sonnet" } }
EOF
  [ ! -d "$(dirname "$MODEL_BUMP_LOG")" ]
  bash "$RESOLVER" haiku >/dev/null
  [ -d "$(dirname "$MODEL_BUMP_LOG")" ]
  [ -f "$MODEL_BUMP_LOG" ]
}

@test "step4: no --caller arg yields empty caller field" {
  cat > "$MODEL_OVERRIDES_JSON" <<'EOF'
{ "tier_aliases": { "haiku": "sonnet" } }
EOF
  bash "$RESOLVER" haiku >/dev/null
  local caller
  caller=$(head -n 1 "$MODEL_BUMP_LOG" | jq -r '.caller')
  [ "$caller" = "" ]
}

@test "step4: missing overrides file is silently allowed (happy path unchanged)" {
  [ ! -e "$MODEL_OVERRIDES_JSON" ]
  run bash "$RESOLVER" haiku
  [ "$status" -eq 0 ]
  [ "$output" = "claude-haiku-4-5-20251001" ]
  [ ! -e "$MODEL_BUMP_LOG" ]
}

@test "step4: overrides file with no tier_aliases is a no-op" {
  cat > "$MODEL_OVERRIDES_JSON" <<'EOF'
{ "tier_aliases": {} }
EOF
  run bash "$RESOLVER" haiku
  [ "$status" -eq 0 ]
  [ "$output" = "claude-haiku-4-5-20251001" ]
  [ ! -e "$MODEL_BUMP_LOG" ]
}

# ---------------------------------------------------------------------------
# Step 5 — cascade + cycle detection
# ---------------------------------------------------------------------------

@test "step5: two-hop cascade haiku→sonnet→opus resolves to opus" {
  cat > "$MODEL_OVERRIDES_JSON" <<'EOF'
{ "tier_aliases": { "haiku": "sonnet", "sonnet": "opus" } }
EOF
  run bash "$RESOLVER" haiku --caller naming-review
  [ "$status" -eq 0 ]
  [ "$output" = "claude-opus-4-8" ]
}

@test "step5: cascade logs exactly one bump line with served=opus" {
  cat > "$MODEL_OVERRIDES_JSON" <<'EOF'
{ "tier_aliases": { "haiku": "sonnet", "sonnet": "opus" } }
EOF
  bash "$RESOLVER" haiku --caller naming-review >/dev/null
  local line_count
  line_count=$(wc -l < "$MODEL_BUMP_LOG" | tr -d ' ')
  [ "$line_count" = "1" ]
  local served
  served=$(jq -r '.served' "$MODEL_BUMP_LOG")
  [ "$served" = "opus" ]
  local requested
  requested=$(jq -r '.requested' "$MODEL_BUMP_LOG")
  [ "$requested" = "haiku" ]
}

@test "step5: cycle haiku→sonnet→haiku exits 3 with cycle message" {
  cat > "$MODEL_OVERRIDES_JSON" <<'EOF'
{ "tier_aliases": { "haiku": "sonnet", "sonnet": "haiku" } }
EOF
  run bash -c "bash '$RESOLVER' haiku 2>&1 1>/dev/null"
  [ "$status" -eq 3 ]
  [[ "$output" == *"Cycle detected in tier aliases:"* ]]
  [[ "$output" == *"haiku"* ]]
  [[ "$output" == *"sonnet"* ]]
}

@test "step5: cycle writes no bump log entry" {
  cat > "$MODEL_OVERRIDES_JSON" <<'EOF'
{ "tier_aliases": { "haiku": "sonnet", "sonnet": "haiku" } }
EOF
  bash "$RESOLVER" haiku >/dev/null 2>&1 || true
  [ ! -e "$MODEL_BUMP_LOG" ]
}

# ---------------------------------------------------------------------------
# Step 6 — exhaustion, missing routing.json, malformed overrides
# ---------------------------------------------------------------------------

@test "step6: opus→unavailable exits 3 with the AC5 exhaustion template" {
  cat > "$MODEL_OVERRIDES_JSON" <<'EOF'
{ "tier_aliases": { "opus": "unavailable" } }
EOF
  run bash -c "bash '$RESOLVER' opus 2>&1 1>/dev/null"
  [ "$status" -eq 3 ]
  [[ "$output" == *"All model tiers exhausted for requested tier 'opus'."* ]]
  [[ "$output" == *"Routing defaults:"* ]]
  [[ "$output" == *"$MODEL_ROUTING_JSON"* ]]
  [[ "$output" == *"\"opus\": \"unavailable\""* ]]
  [[ "$output" == *"/model-routing-check"* ]]
}

@test "step6: exhaustion writes no bump log entry" {
  cat > "$MODEL_OVERRIDES_JSON" <<'EOF'
{ "tier_aliases": { "opus": "unavailable" } }
EOF
  bash "$RESOLVER" opus >/dev/null 2>&1 || true
  [ ! -e "$MODEL_BUMP_LOG" ]
}

@test "step6: missing routing.json exits 4 with remediation" {
  export MODEL_ROUTING_JSON="$BATS_TMPDIR_CASE/does-not-exist.json"
  run bash -c "bash '$RESOLVER' haiku 2>&1 1>/dev/null"
  [ "$status" -eq 4 ]
  [[ "$output" == *"Model routing file missing:"* ]]
  [[ "$output" == *"git checkout knowledge/model-routing.json"* ]]
}

@test "step6: malformed overrides file exits 5 with remediation" {
  echo '{not valid json' > "$MODEL_OVERRIDES_JSON"
  run bash -c "bash '$RESOLVER' haiku 2>&1 1>/dev/null"
  [ "$status" -eq 5 ]
  [[ "$output" == *"Override file is not valid JSON:"* ]]
  [[ "$output" == *"$MODEL_OVERRIDES_JSON"* ]]
  [[ "$output" == *"delete"* ]] || [[ "$output" == *"fix"* ]]
}

# ---------------------------------------------------------------------------
# Step 7 — --dump-map flag
# ---------------------------------------------------------------------------

@test "step7: --dump-map prints the three default tiers" {
  run bash "$RESOLVER" --dump-map
  [ "$status" -eq 0 ]
  [[ "$output" == *"haiku"* ]]
  [[ "$output" == *"sonnet"* ]]
  [[ "$output" == *"opus"* ]]
  [[ "$output" == *"claude-haiku-4-5-20251001"* ]]
  [[ "$output" == *"claude-sonnet-4-6"* ]]
  [[ "$output" == *"claude-opus-4-8"* ]]
}

@test "step7: --dump-map reflects overrides when present" {
  cat > "$MODEL_OVERRIDES_JSON" <<'EOF'
{ "tier_aliases": { "haiku": "sonnet" } }
EOF
  run bash "$RESOLVER" --dump-map
  [ "$status" -eq 0 ]
  # haiku now resolves to the sonnet snapshot
  [[ "$output" == *"claude-sonnet-4-6"* ]]
}

@test "step7: --dump-map writes no files" {
  bash "$RESOLVER" --dump-map >/dev/null
  [ ! -e "$MODEL_BUMP_LOG" ]
}
