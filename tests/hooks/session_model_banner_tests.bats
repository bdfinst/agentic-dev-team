#!/usr/bin/env bats
# Tests for hooks/session-model-banner.sh — the single SessionStart hook that
# captures + persists the session model and announces the effort band→model
# routing table. Replaces the retired overrides-banner.sh. AC4.

HOOK="$BATS_TEST_DIRNAME/../../plugins/dev-team/hooks/session-model-banner.sh"
OLD_HOOK="$BATS_TEST_DIRNAME/../../plugins/dev-team/hooks/overrides-banner.sh"
SETTINGS_JSON="$BATS_TEST_DIRNAME/../../plugins/dev-team/settings.json"

setup() {
  BATS_TMPDIR_CASE="$(mktemp -d)"
  mkdir -p "$BATS_TMPDIR_CASE/knowledge"
  cat > "$BATS_TMPDIR_CASE/knowledge/model-routing.json" <<'EOF'
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
  export MODEL_ROUTING_JSON="$BATS_TMPDIR_CASE/knowledge/model-routing.json"
  export MODEL_LADDER_JSON="$BATS_TMPDIR_CASE/.claude/model-ladder.json"
  export SESSION_MODEL_FILE="$BATS_TMPDIR_CASE/.claude/session-model"
}

teardown() {
  rm -rf "$BATS_TMPDIR_CASE"
  unset MODEL_ROUTING_JSON MODEL_LADDER_JSON SESSION_MODEL_FILE
}

_session_start_input() {
  local model="${1:-}"
  if [[ -n "$model" ]]; then
    jq -nc --arg cwd "$BATS_TMPDIR_CASE" --arg m "$model" \
      '{hook_event_name:"SessionStart", cwd:$cwd, model:$m}'
  else
    jq -nc --arg cwd "$BATS_TMPDIR_CASE" \
      '{hook_event_name:"SessionStart", cwd:$cwd}'
  fi
}

# ---------------------------------------------------------------------------
# Step 2.1 — capture + persist; retire the old hook
# ---------------------------------------------------------------------------

@test "captures and persists the session model from the payload" {
  local input
  input=$(_session_start_input "claude-sonnet-4-6")
  run bash -c "echo '$input' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  [ -f "$SESSION_MODEL_FILE" ]
  [ "$(cat "$SESSION_MODEL_FILE")" = "claude-sonnet-4-6" ]
}

@test "malformed stdin fails open (silent, exit 0)" {
  run bash -c "echo 'not json' | bash '$HOOK'"
  [ "$status" -eq 0 ]
}

@test "Security: a session model with unsafe characters is not persisted" {
  run bash -c "echo '$(_session_start_input "evil; rm -rf /")' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  [ ! -s "$SESSION_MODEL_FILE" ]
}

@test "the retired overrides-banner.sh no longer exists" {
  [ ! -e "$OLD_HOOK" ]
}

@test "settings.json registers session-model-banner.sh, not overrides-banner.sh" {
  run jq -e '.hooks.SessionStart[] | .hooks[] | select(.command | contains("session-model-banner.sh"))' "$SETTINGS_JSON"
  [ "$status" -eq 0 ]
  run jq -e '[.hooks.SessionStart[] | .hooks[] | select(.command | contains("overrides-banner.sh"))] | length == 0' "$SETTINGS_JSON"
  [ "$status" -eq 0 ]
}

# ---------------------------------------------------------------------------
# Step 2.2 — banner rendering (band→model table, flags, degenerate cases)
# ---------------------------------------------------------------------------

# Capture the banner (stderr) for a given SessionStart payload.
_banner() {
  local model="${1:-}"
  bash -c "echo '$(_session_start_input "$model")' | bash '$HOOK' 2>&1 1>/dev/null"
}

@test "banner: no-ladder lists the default band→model map" {
  run _banner "claude-sonnet-4-6"
  [[ "$output" == *"low"*"claude-haiku-4-5-20251001"* ]]
  [[ "$output" == *"medium"*"claude-sonnet-4-6"* ]]
  [[ "$output" == *"high"*"claude-opus-4-8"* ]]
}

@test "banner: no-ladder names the ladder path as the override hint" {
  run _banner "claude-sonnet-4-6"
  [[ "$output" == *".claude/model-ladder.json"* ]]
}

@test "banner: flags a band whose model is above the session model" {
  # session = sonnet (medium). high → opus is above session.
  run _banner "claude-sonnet-4-6"
  # The high line carries an above-session marker; low/medium do not.
  echo "$output" | grep -E 'high.*claude-opus-4-8' | grep -qi 'above'
  ! { echo "$output" | grep -E 'low.*claude-haiku' | grep -qi 'above'; }
}

@test "banner: session at the top of the ladder shows no upgrade flags" {
  run _banner "claude-opus-4-8"
  ! echo "$output" | grep -qi 'above'
}

@test "banner: single-model ladder collapses to one line" {
  mkdir -p "$(dirname "$MODEL_LADDER_JSON")"
  echo '["claude-sonnet-4-6"]' > "$MODEL_LADDER_JSON"
  run _banner "claude-sonnet-4-6"
  [[ "$output" == *"claude-sonnet-4-6"* ]]
  [[ "$output" == *"all effort bands"* || "$output" == *"single-model"* ]]
}

@test "banner: ladder is reflected in the table" {
  mkdir -p "$(dirname "$MODEL_LADDER_JSON")"
  echo '["claude-sonnet-4-6", "claude-opus-4-8"]' > "$MODEL_LADDER_JSON"
  run _banner "claude-sonnet-4-6"
  # low → bottom of ladder (sonnet); high → top (opus)
  [[ "$output" == *"low"*"claude-sonnet-4-6"* ]]
  [[ "$output" == *"high"*"claude-opus-4-8"* ]]
}

@test "banner: absent model with a persisted value reuses it" {
  mkdir -p "$(dirname "$SESSION_MODEL_FILE")"
  printf 'claude-opus-4-8\n' > "$SESSION_MODEL_FILE"
  run _banner ""   # no model in payload
  [ "$status" -eq 0 ]
  # Rendered using the persisted opus → session at top → no upgrade flags.
  ! echo "$output" | grep -qi 'above'
  # The persisted file is not clobbered.
  [ "$(cat "$SESSION_MODEL_FILE")" = "claude-opus-4-8" ]
}

@test "banner: absent model with nothing persisted is explained, no error" {
  run _banner ""
  [ "$status" -eq 0 ]
  [[ "$output" == *"unknown"* ]]
}
