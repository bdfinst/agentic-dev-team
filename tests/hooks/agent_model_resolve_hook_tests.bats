#!/usr/bin/env bats
# Tests for hooks/agent-model-resolve.sh — PreToolUse hook registered on the
# "Agent" matcher. The hook reads PreToolUse-shaped JSON from stdin, looks up
# the dispatched agent's effort band from agents/<subagent_type>.md, resolves
# it via hooks/lib/model-resolve.sh, and rewrites tool_input.model:
#   - effort agent:    updatedInput sets model to the resolved snapshot (always)
#   - legacy tier:     tool_input.model tier → band → snapshot + deprecation marker
#   - unknown agent:   pass-through {} when no usable band is found
#   - resolver error:  fail-open {} (incl. missing routing.json — never deny)
#
# AC2, AC3, AC5.

HOOK="$BATS_TEST_DIRNAME/../../plugins/dev-team/hooks/agent-model-resolve.sh"
SETTINGS_JSON="$BATS_TEST_DIRNAME/../../plugins/dev-team/settings.json"

setup() {
  BATS_TMPDIR_CASE="$(mktemp -d)"
  mkdir -p "$BATS_TMPDIR_CASE/knowledge" "$BATS_TMPDIR_CASE/agents"
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
  # Stub agents declaring effort bands.
  printf -- '---\nname: high-agent\neffort: high\n---\nbody\n' > "$BATS_TMPDIR_CASE/agents/high-agent.md"
  printf -- '---\nname: low-agent\neffort: low\n---\nbody\n' > "$BATS_TMPDIR_CASE/agents/low-agent.md"
  printf -- '---\nname: security-review\neffort: high\n---\nbody\n' > "$BATS_TMPDIR_CASE/agents/security-review.md"

  export MODEL_ROUTING_JSON="$BATS_TMPDIR_CASE/knowledge/model-routing.json"
  export MODEL_AGENTS_DIR="$BATS_TMPDIR_CASE/agents"
  export MODEL_LADDER_JSON="$BATS_TMPDIR_CASE/.claude/model-ladder.json"  # absent by default
  export SESSION_MODEL_FILE="$BATS_TMPDIR_CASE/.claude/session-model"     # absent by default
  export MODEL_BUMP_LOG="$BATS_TMPDIR_CASE/.claude/metrics/model-routing.log"
}

teardown() {
  rm -rf "$BATS_TMPDIR_CASE"
  unset MODEL_ROUTING_JSON MODEL_AGENTS_DIR MODEL_LADDER_JSON SESSION_MODEL_FILE MODEL_BUMP_LOG
}

# Build PreToolUse Agent input. Omits model when "$2" is empty.
_agent_input() {
  local subagent_type="$1" model="${2:-}"
  if [[ -n "$model" ]]; then
    jq -nc --arg s "$subagent_type" --arg m "$model" \
      '{tool_name:"Agent", tool_input:{subagent_type:$s, model:$m, description:"test", prompt:"test"}}'
  else
    jq -nc --arg s "$subagent_type" \
      '{tool_name:"Agent", tool_input:{subagent_type:$s, description:"test", prompt:"test"}}'
  fi
}

# ---------------------------------------------------------------------------
# Effort-band resolution (the primary path)
# ---------------------------------------------------------------------------

@test "effort high, no ladder → rewrites model to opus, logs no bump (AC5)" {
  run bash -c "echo '$(_agent_input high-agent)' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e . >/dev/null
  [ "$(echo "$output" | jq -r '.hookSpecificOutput.updatedInput.model')" = "claude-opus-4-8" ]
  [ "$(echo "$output" | jq -r '.hookSpecificOutput.hookEventName')" = "PreToolUse" ]
  # Equal to the band default → no bump line.
  [ ! -e "$MODEL_BUMP_LOG" ]
}

@test "effort agent always rewrites model even when equal to default (AC5, not pass-through)" {
  run bash -c "echo '$(_agent_input high-agent)' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  [ "$output" != "{}" ]
  echo "$output" | jq -e '.hookSpecificOutput.updatedInput.model' >/dev/null
}

@test "effort high WITH ladder that changes the result → ladder model + one bump" {
  mkdir -p "$(dirname "$MODEL_LADDER_JSON")"
  cat > "$MODEL_LADDER_JSON" <<'EOF'
["claude-haiku-4-5-20251001", "claude-sonnet-4-6"]
EOF
  run bash -c "echo '$(_agent_input high-agent)' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  # N=2, high → index 1 → sonnet
  [ "$(echo "$output" | jq -r '.hookSpecificOutput.updatedInput.model')" = "claude-sonnet-4-6" ]
  [ -f "$MODEL_BUMP_LOG" ]
  [ "$(wc -l < "$MODEL_BUMP_LOG" | tr -d ' ')" = "1" ]
  [ "$(head -n1 "$MODEL_BUMP_LOG" | jq -r '.band')" = "high" ]
  [ "$(head -n1 "$MODEL_BUMP_LOG" | jq -r '.served')" = "claude-sonnet-4-6" ]
  [ "$(head -n1 "$MODEL_BUMP_LOG" | jq -r '.reason')" = "effort" ]
  [ "$(head -n1 "$MODEL_BUMP_LOG" | jq -r '.caller')" = "high-agent" ]
}

@test "plugin-qualified subagent_type resolves the right agent file" {
  run bash -c "echo '$(_agent_input dev-team:security-review)' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  [ "$(echo "$output" | jq -r '.hookSpecificOutput.updatedInput.model')" = "claude-opus-4-8" ]
}

# ---------------------------------------------------------------------------
# Legacy tier fallback + deprecation marker (AC3)
# ---------------------------------------------------------------------------

@test "legacy model: sonnet (no effort agent) → medium snapshot + deprecation marker" {
  run bash -c "echo '$(_agent_input legacy-agent sonnet)' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  [ "$(echo "$output" | jq -r '.hookSpecificOutput.updatedInput.model')" = "claude-sonnet-4-6" ]
  [ -f "$MODEL_BUMP_LOG" ]
  [ "$(head -n1 "$MODEL_BUMP_LOG" | jq -r '.reason')" = "legacy-tier" ]
  [ "$(head -n1 "$MODEL_BUMP_LOG" | jq -r '.band')" = "medium" ]
}

# ---------------------------------------------------------------------------
# Pass-through and fail-open cases
# ---------------------------------------------------------------------------

@test "unknown subagent_type with no model → pass-through {}" {
  run bash -c "echo '$(_agent_input does-not-exist)' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  [ "$output" = "{}" ]
  [ ! -e "$MODEL_BUMP_LOG" ]
}

@test "missing routing.json (resolver exit 4) → pass-through, not deny (fail-open)" {
  export MODEL_ROUTING_JSON="$BATS_TMPDIR_CASE/missing.json"
  run bash -c "echo '$(_agent_input high-agent)' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  [ "$output" = "{}" ]
  # Never emits a deny envelope.
  ! echo "$output" | jq -e '.hookSpecificOutput.permissionDecision' >/dev/null 2>&1
}

@test "non-Agent tool name is a no-op (empty stdout, exit 0)" {
  local input
  input=$(jq -nc '{tool_name:"Bash", tool_input:{command:"ls"}}')
  run bash -c "echo '$input' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "malformed stdin JSON fails open (empty stdout, exit 0)" {
  run bash -c "echo 'not json' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

# ---------------------------------------------------------------------------
# Slice 3 — session-model fallback, no ceiling, silent-but-logged
# ---------------------------------------------------------------------------

@test "Step 3.1: no ladder + effort band resolves to the default map, not the session model" {
  mkdir -p "$(dirname "$SESSION_MODEL_FILE")"
  printf 'claude-haiku-4-5-20251001\n' > "$SESSION_MODEL_FILE"  # session = haiku
  run bash -c "echo '$(_agent_input high-agent)' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  # high → opus (default map), NOT the session model (haiku).
  [ "$(echo "$output" | jq -r '.hookSpecificOutput.updatedInput.model')" = "claude-opus-4-8" ]
}

@test "Step 3.1: explicit snapshot absent from the ladder falls back to the session model" {
  mkdir -p "$(dirname "$MODEL_LADDER_JSON")" "$(dirname "$SESSION_MODEL_FILE")"
  echo '["claude-sonnet-4-6", "claude-opus-4-8"]' > "$MODEL_LADDER_JSON"
  printf 'claude-sonnet-4-6\n' > "$SESSION_MODEL_FILE"
  # Dispatch an unknown agent with an explicit snapshot NOT in the ladder.
  run bash -c "echo '$(_agent_input some-agent claude-opusmax-9)' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  [ "$(echo "$output" | jq -r '.hookSpecificOutput.updatedInput.model')" = "claude-sonnet-4-6" ]
  [ "$(head -n1 "$MODEL_BUMP_LOG" | jq -r '.reason')" = "session-fallback" ]
}

@test "Step 3.1: explicit snapshot present in the ladder is passed through" {
  mkdir -p "$(dirname "$MODEL_LADDER_JSON")" "$(dirname "$SESSION_MODEL_FILE")"
  echo '["claude-sonnet-4-6", "claude-opus-4-8"]' > "$MODEL_LADDER_JSON"
  printf 'claude-sonnet-4-6\n' > "$SESSION_MODEL_FILE"
  run bash -c "echo '$(_agent_input some-agent claude-opus-4-8)' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  [ "$output" = "{}" ]
}

@test "Step 3.1: explicit snapshot with no ladder is passed through" {
  run bash -c "echo '$(_agent_input some-agent claude-opusmax-9)' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  [ "$output" = "{}" ]
}

@test "Step 3.2: high agent runs above a lower session model (no ceiling, no message)" {
  mkdir -p "$(dirname "$MODEL_LADDER_JSON")" "$(dirname "$SESSION_MODEL_FILE")"
  echo '["claude-haiku-4-5-20251001", "claude-sonnet-4-6", "claude-opus-4-8"]' > "$MODEL_LADDER_JSON"
  printf 'claude-sonnet-4-6\n' > "$SESSION_MODEL_FILE"  # session = sonnet (middle)
  run bash -c "echo '$(_agent_input high-agent)' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  # high → top of ladder (opus), above the session model.
  [ "$(echo "$output" | jq -r '.hookSpecificOutput.updatedInput.model')" = "claude-opus-4-8" ]
  # Silent: no deny / permissionDecision / systemMessage.
  ! echo "$output" | jq -e '.hookSpecificOutput.permissionDecision' >/dev/null 2>&1
  ! echo "$output" | jq -e '.systemMessage' >/dev/null 2>&1
}

@test "Step 3.2: an upgrade logs exactly one line carrying the session model" {
  mkdir -p "$(dirname "$MODEL_LADDER_JSON")" "$(dirname "$SESSION_MODEL_FILE")"
  echo '["claude-haiku-4-5-20251001", "claude-sonnet-4-6", "claude-opus-4-8", "claude-opusmax-9"]' > "$MODEL_LADDER_JSON"
  printf 'claude-opus-4-8\n' > "$SESSION_MODEL_FILE"
  run bash -c "echo '$(_agent_input high-agent)' | bash '$HOOK'"
  # high → max (≠ opus default) = upgrade
  [ "$(echo "$output" | jq -r '.hookSpecificOutput.updatedInput.model')" = "claude-opusmax-9" ]
  [ "$(wc -l < "$MODEL_BUMP_LOG" | tr -d ' ')" = "1" ]
  [ "$(head -n1 "$MODEL_BUMP_LOG" | jq -r '.served')" = "claude-opusmax-9" ]
  [ "$(head -n1 "$MODEL_BUMP_LOG" | jq -r '.session')" = "claude-opus-4-8" ]
}

@test "Step 3.2: a downgrade logs exactly one line" {
  mkdir -p "$(dirname "$MODEL_LADDER_JSON")"
  echo '["claude-haiku-4-5-20251001", "claude-sonnet-4-6"]' > "$MODEL_LADDER_JSON"
  run bash -c "echo '$(_agent_input high-agent)' | bash '$HOOK'"
  # high → sonnet (≠ opus default) = downgrade
  [ "$(echo "$output" | jq -r '.hookSpecificOutput.updatedInput.model')" = "claude-sonnet-4-6" ]
  [ "$(wc -l < "$MODEL_BUMP_LOG" | tr -d ' ')" = "1" ]
  [ "$(head -n1 "$MODEL_BUMP_LOG" | jq -r '.served')" = "claude-sonnet-4-6" ]
}

# ---------------------------------------------------------------------------
# AC18 — settings.json registration (unchanged filename)
# ---------------------------------------------------------------------------

@test "AC18: settings.json registers agent-model-resolve.sh under PreToolUse Agent matcher" {
  [ -f "$SETTINGS_JSON" ]
  run jq -e '.hooks.PreToolUse[] | select(.matcher == "Agent") | .hooks[] | select(.command | contains("agent-model-resolve.sh"))' "$SETTINGS_JSON"
  [ "$status" -eq 0 ]
}
