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

RESOLVER="$BATS_TEST_DIRNAME/../../plugins/agentic-dev-team/hooks/lib/model-resolve.sh"

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
