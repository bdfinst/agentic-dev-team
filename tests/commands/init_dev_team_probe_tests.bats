#!/usr/bin/env bats
# Tests for the /init-dev-team probe sub-step and hooks/lib/model-probe.sh.
#
# Steps 11-14 + AC7, AC7a, AC7b, AC8, AC9.
#
# The probe shells out to curl. Tests inject a deterministic fake curl on
# PATH (tests/hooks/fake-bin/curl) and select fixtures via env vars the
# fake reads at runtime.

INIT_MD="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/init-dev-team/SKILL.md"
PROBE="$BATS_TEST_DIRNAME/../../plugins/dev-team/hooks/lib/model-probe.sh"
FAKE_BIN="$BATS_TEST_DIRNAME/../hooks/fake-bin"
SENTINEL="" # set in setup

setup() {
  BATS_TMPDIR_CASE="$(mktemp -d)"
  mkdir -p "$BATS_TMPDIR_CASE/knowledge" "$BATS_TMPDIR_CASE/.claude"
  cat > "$BATS_TMPDIR_CASE/knowledge/model-routing.json" <<'EOF'
{
  "haiku": "claude-haiku-4-5-20251001",
  "sonnet": "claude-sonnet-4-6",
  "opus": "claude-opus-4-8"
}
EOF
  export MODEL_ROUTING_JSON="$BATS_TMPDIR_CASE/knowledge/model-routing.json"
  export MODEL_OVERRIDES_JSON="$BATS_TMPDIR_CASE/.claude/model-overrides.json"
  SENTINEL="$BATS_TMPDIR_CASE/curl-called.sentinel"
  export MODEL_PROBE_CURL_SENTINEL="$SENTINEL"
  rm -f "$SENTINEL"
  # The test harness may have ANTHROPIC_BASE_URL set (e.g., corporate proxy).
  # Unset by default so the "supported endpoint" path runs; individual tests
  # set it explicitly via `run` invocation when verifying non-Anthropic gating.
  unset ANTHROPIC_BASE_URL
  # The curl shim is checked in at tests/hooks/fake-bin/curl. Prepend it
  # to PATH so the probe's `curl` invocation hits the fake first.
  [[ -x "$FAKE_BIN/curl" ]] || skip "fake-bin/curl missing or not executable"
  export PATH="$FAKE_BIN:$PATH"
}

teardown() {
  rm -rf "$BATS_TMPDIR_CASE"
  unset MODEL_ROUTING_JSON MODEL_OVERRIDES_JSON MODEL_PROBE_CURL_SENTINEL
  unset MODEL_PROBE_FAKE_MODE ANTHROPIC_BASE_URL MODEL_PROBE_TIMEOUT
  # Don't remove the shim — it's reused across tests and harmless on PATH
}

# ---------------------------------------------------------------------------
# Step 11 — doc-inspection: prompt text is verbatim
# ---------------------------------------------------------------------------

@test "doc: init-dev-team.md contains probe sub-step heading" {
  grep -qE "^##.*Probe model availability" "$INIT_MD"
}

@test "doc: probe section contains the verbatim prompt text" {
  grep -q "Probe Anthropic's model list to detect which tiers are available?" "$INIT_MD"
  grep -q "Probe model availability? \[y/N\]" "$INIT_MD"
  grep -q "What this does:" "$INIT_MD"
  grep -q "What it writes:" "$INIT_MD"
  grep -q "What it skips:" "$INIT_MD"
  grep -q 'Default is "n"' "$INIT_MD"
}

# ---------------------------------------------------------------------------
# Step 11 — AC7: decline writes nothing
# ---------------------------------------------------------------------------

@test "AC7: probe with input 'n' writes no overrides file and exits 0" {
  echo "n" | run bash "$PROBE"
  run bash -c "echo 'n' | bash '$PROBE'"
  [ "$status" -eq 0 ]
  [ ! -e "$MODEL_OVERRIDES_JSON" ]
  [ ! -e "$SENTINEL" ]  # curl not invoked on decline
}

@test "AC7: probe with empty input (default no) writes no overrides file" {
  run bash -c "echo '' | bash '$PROBE'"
  [ "$status" -eq 0 ]
  [ ! -e "$MODEL_OVERRIDES_JSON" ]
}

# ---------------------------------------------------------------------------
# Step 12 — AC7a: accept, all tiers available
# ---------------------------------------------------------------------------

@test "AC7a: accept + all-tiers-available writes no overrides; emits 'All model tiers available' message" {
  MODEL_PROBE_FAKE_MODE=ok-all run bash -c "echo 'y' | bash '$PROBE' 2>&1"
  [ "$status" -eq 0 ]
  [ ! -e "$MODEL_OVERRIDES_JSON" ]
  [[ "$output" == *"All model tiers available; no overrides needed."* ]]
  [ -e "$SENTINEL" ]  # curl invoked
}

# ---------------------------------------------------------------------------
# Step 12 — AC7b: accept, haiku snapshot missing → write overrides
# ---------------------------------------------------------------------------

@test "AC7b: accept + missing haiku snapshot writes overrides with tier_aliases.haiku=sonnet" {
  MODEL_PROBE_FAKE_MODE=missing run bash -c "echo 'y' | bash '$PROBE'"
  [ "$status" -eq 0 ]
  [ -f "$MODEL_OVERRIDES_JSON" ]
  [ "$(jq -r '.tier_aliases.haiku' "$MODEL_OVERRIDES_JSON")" = "sonnet" ]
  [ "$(jq -r '.reason' "$MODEL_OVERRIDES_JSON")" = "haiku snapshot not in /v1/models response" ]
}

@test "AC7b: overrides file includes available_models matching the response" {
  MODEL_PROBE_FAKE_MODE=missing bash -c "echo 'y' | bash '$PROBE'" >/dev/null 2>&1
  local count
  count=$(jq -r '.available_models | length' "$MODEL_OVERRIDES_JSON")
  [ "$count" = "2" ]
  jq -e '.available_models | index("claude-sonnet-4-6")' "$MODEL_OVERRIDES_JSON" >/dev/null
  jq -e '.available_models | index("claude-opus-4-8")' "$MODEL_OVERRIDES_JSON" >/dev/null
}

@test "AC7b: overrides file generated_at is parseable ISO-8601" {
  MODEL_PROBE_FAKE_MODE=missing bash -c "echo 'y' | bash '$PROBE'" >/dev/null 2>&1
  local ts
  ts=$(jq -r '.generated_at' "$MODEL_OVERRIDES_JSON")
  [[ "$ts" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]]
}

@test "AC7b: user message is the literal bumped-tier string" {
  MODEL_PROBE_FAKE_MODE=missing run bash -c "echo 'y' | bash '$PROBE' 2>&1"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Model tier 'haiku' bumped to 'sonnet'; .claude/model-overrides.json written."* ]]
}

# ---------------------------------------------------------------------------
# Step 13 — AC8: non-Anthropic base URL skips the probe entirely
# ---------------------------------------------------------------------------

@test "AC8: Bedrock URL skips probe — no HTTP, no overrides, references docs" {
  ANTHROPIC_BASE_URL="https://bedrock-runtime.us-east-1.amazonaws.com" \
    MODEL_PROBE_FAKE_MODE=ok-all \
    run bash -c "echo 'y' | bash '$PROBE' 2>&1"
  [ "$status" -eq 0 ]
  [ ! -e "$SENTINEL" ]
  [ ! -e "$MODEL_OVERRIDES_JSON" ]
  [[ "$output" == *"Probe skipped:"* ]]
  [[ "$output" == *"bedrock-runtime.us-east-1.amazonaws.com"* ]]
  [[ "$output" == *"docs/model-routing.md"* ]]
}

@test "AC8: Vertex URL skips probe with the same wording" {
  ANTHROPIC_BASE_URL="https://aiplatform.googleapis.com" \
    MODEL_PROBE_FAKE_MODE=ok-all \
    run bash -c "echo 'y' | bash '$PROBE' 2>&1"
  [ "$status" -eq 0 ]
  [ ! -e "$SENTINEL" ]
  [ ! -e "$MODEL_OVERRIDES_JSON" ]
  [[ "$output" == *"Probe skipped:"* ]]
}

@test "AC8: api.anthropic.com proceeds with the probe" {
  ANTHROPIC_BASE_URL="https://api.anthropic.com" \
    MODEL_PROBE_FAKE_MODE=ok-all \
    run bash -c "echo 'y' | bash '$PROBE' 2>&1"
  [ "$status" -eq 0 ]
  [ -e "$SENTINEL" ]
}

# ---------------------------------------------------------------------------
# Step 14 — AC9: three differentiated failure messages
# ---------------------------------------------------------------------------

@test "AC9: timeout (exit 28) writes no overrides; message starts with 'Probe timed out'" {
  MODEL_PROBE_FAKE_MODE=timeout run bash -c "echo 'y' | bash '$PROBE' 2>&1"
  [ "$status" -eq 0 ]
  [ ! -e "$MODEL_OVERRIDES_JSON" ]
  [[ "$output" == *"Probe timed out after 5s:"* ]]
  [[ "$output" == *"Dispatch fallback still applies; see docs/model-routing.md."* ]]
}

@test "AC9: HTTP 500 message starts with 'Probe endpoint returned HTTP 500'" {
  MODEL_PROBE_FAKE_MODE=http500 run bash -c "echo 'y' | bash '$PROBE' 2>&1"
  [ "$status" -eq 0 ]
  [ ! -e "$MODEL_OVERRIDES_JSON" ]
  [[ "$output" == *"Probe endpoint returned HTTP 500:"* ]]
  [[ "$output" == *"Dispatch fallback still applies; see docs/model-routing.md."* ]]
}

@test "AC9: malformed JSON message starts with 'Probe response was not valid JSON'" {
  MODEL_PROBE_FAKE_MODE=bad-json run bash -c "echo 'y' | bash '$PROBE' 2>&1"
  [ "$status" -eq 0 ]
  [ ! -e "$MODEL_OVERRIDES_JSON" ]
  [[ "$output" == *"Probe response was not valid JSON:"* ]]
  [[ "$output" == *"Dispatch fallback still applies; see docs/model-routing.md."* ]]
}
