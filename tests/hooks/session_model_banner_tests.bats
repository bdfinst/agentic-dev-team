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

@test "the retired overrides-banner.sh no longer exists" {
  [ ! -e "$OLD_HOOK" ]
}

@test "settings.json registers session-model-banner.sh, not overrides-banner.sh" {
  run jq -e '.hooks.SessionStart[] | .hooks[] | select(.command | contains("session-model-banner.sh"))' "$SETTINGS_JSON"
  [ "$status" -eq 0 ]
  run jq -e '[.hooks.SessionStart[] | .hooks[] | select(.command | contains("overrides-banner.sh"))] | length == 0' "$SETTINGS_JSON"
  [ "$status" -eq 0 ]
}
