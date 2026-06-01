#!/usr/bin/env bats
# Tests for hooks/agent-model-resolve.sh — PreToolUse hook registered on
# the "Agent" matcher. The hook reads Claude Code PreToolUse-shaped JSON
# from stdin, shells out to hooks/lib/model-resolve.sh, and emits the
# appropriate hookSpecificOutput:
#   - on bump:        updatedInput rewrites tool_input.model
#   - on pass-through (no override): empty object {} (no change)
#   - on refusal (resolver exit 3/4/5): permissionDecision="deny" with the
#                                       resolver's stderr as the reason
#
# AC16, AC17, AC18.

HOOK="$BATS_TEST_DIRNAME/../../plugins/agentic-dev-team/hooks/agent-model-resolve.sh"
RESOLVER="$BATS_TEST_DIRNAME/../../plugins/agentic-dev-team/hooks/lib/model-resolve.sh"
SETTINGS_JSON="$BATS_TEST_DIRNAME/../../plugins/agentic-dev-team/settings.json"

setup() {
  BATS_TMPDIR_CASE="$(mktemp -d)"
  # Fixture routing.json mirrors plugin defaults.
  mkdir -p "$BATS_TMPDIR_CASE/knowledge"
  cat > "$BATS_TMPDIR_CASE/knowledge/model-routing.json" <<'EOF'
{
  "haiku": "claude-haiku-4-5-20251001",
  "sonnet": "claude-sonnet-4-6",
  "opus": "claude-opus-4-8"
}
EOF
  export MODEL_ROUTING_JSON="$BATS_TMPDIR_CASE/knowledge/model-routing.json"
  export MODEL_OVERRIDES_JSON="$BATS_TMPDIR_CASE/.claude/model-overrides.json"
  export MODEL_BUMP_LOG="$BATS_TMPDIR_CASE/.claude/metrics/model-routing.log"
  mkdir -p "$(dirname "$MODEL_OVERRIDES_JSON")"
}

teardown() {
  rm -rf "$BATS_TMPDIR_CASE"
  unset MODEL_ROUTING_JSON MODEL_OVERRIDES_JSON MODEL_BUMP_LOG
}

# Helper: build a PreToolUse-shaped JSON for the Agent tool.
_pretooluse_agent_input() {
  local model="$1" subagent_type="${2:-naming-review}"
  jq -nc \
    --arg model "$model" \
    --arg subagent_type "$subagent_type" \
    --arg cwd "$BATS_TMPDIR_CASE" \
    '{
      tool_name: "Agent",
      cwd: $cwd,
      tool_input: {
        model: $model,
        subagent_type: $subagent_type,
        description: "test",
        prompt: "test"
      }
    }'
}

# ---------------------------------------------------------------------------
# Step 8 — AC16: rewrite tool_input.model when an override applies
# ---------------------------------------------------------------------------

@test "hook: AC16 override haiku→sonnet rewrites model to claude-sonnet-4-6" {
  cat > "$MODEL_OVERRIDES_JSON" <<'EOF'
{ "tier_aliases": { "haiku": "sonnet" } }
EOF
  local input
  input=$(_pretooluse_agent_input "haiku" "naming-review")
  run bash -c "echo '$input' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  # Output must be valid JSON
  echo "$output" | jq -e . >/dev/null
  # updatedInput.model rewritten
  local new_model
  new_model=$(echo "$output" | jq -r '.hookSpecificOutput.updatedInput.model')
  [ "$new_model" = "claude-sonnet-4-6" ]
  # hookEventName is set
  local event
  event=$(echo "$output" | jq -r '.hookSpecificOutput.hookEventName')
  [ "$event" = "PreToolUse" ]
  # All other tool_input fields are preserved (only model is rewritten).
  [ "$(echo "$output" | jq -r '.hookSpecificOutput.updatedInput.subagent_type')" = "naming-review" ]
  [ "$(echo "$output" | jq -r '.hookSpecificOutput.updatedInput.description')" = "test" ]
  [ "$(echo "$output" | jq -r '.hookSpecificOutput.updatedInput.prompt')" = "test" ]
}

@test "hook: bump on rewrite appends one log line with caller=subagent_type" {
  cat > "$MODEL_OVERRIDES_JSON" <<'EOF'
{ "tier_aliases": { "haiku": "sonnet" } }
EOF
  local input
  input=$(_pretooluse_agent_input "haiku" "naming-review")
  echo "$input" | bash "$HOOK" >/dev/null
  [ -f "$MODEL_BUMP_LOG" ]
  local caller
  caller=$(head -n 1 "$MODEL_BUMP_LOG" | jq -r '.caller')
  [ "$caller" = "naming-review" ]
}

@test "hook: pass-through (no overrides) emits exactly {}" {
  # No overrides file
  local input
  input=$(_pretooluse_agent_input "haiku" "naming-review")
  run bash -c "echo '$input' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  [ "$output" = "{}" ]
}

@test "hook: pass-through writes no bump log" {
  local input
  input=$(_pretooluse_agent_input "haiku" "naming-review")
  echo "$input" | bash "$HOOK" >/dev/null
  [ ! -e "$MODEL_BUMP_LOG" ]
}

@test "hook: non-Agent tool name is a no-op (empty stdout, exit 0)" {
  local input
  input=$(jq -nc '{tool_name: "Bash", tool_input: {command: "ls"}}')
  run bash -c "echo '$input' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "hook: missing tool_input.model is a no-op" {
  local input
  input=$(jq -nc '{tool_name: "Agent", tool_input: {description: "x"}}')
  run bash -c "echo '$input' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  [ "$output" = "{}" ]
}

@test "hook: malformed stdin JSON fails open (empty stdout, exit 0)" {
  run bash -c "echo 'not json' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "hook: tool_input.model that is already a snapshot ID is left alone" {
  # When the model field is already a full snapshot (passed-through), no
  # rewrite is necessary. Treat snapshot IDs as opaque pass-through.
  local input
  input=$(_pretooluse_agent_input "claude-sonnet-4-6" "naming-review")
  run bash -c "echo '$input' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  [ "$output" = "{}" ]
}

# ---------------------------------------------------------------------------
# Step 9 — AC17: refusal on resolver exit 3/4/5
# ---------------------------------------------------------------------------

@test "hook: AC17 exhausted opus emits permissionDecision=deny" {
  cat > "$MODEL_OVERRIDES_JSON" <<'EOF'
{ "tier_aliases": { "opus": "unavailable" } }
EOF
  local input
  input=$(_pretooluse_agent_input "opus" "security-review")
  run bash -c "echo '$input' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  local decision
  decision=$(echo "$output" | jq -r '.hookSpecificOutput.permissionDecision')
  [ "$decision" = "deny" ]
  local reason
  reason=$(echo "$output" | jq -r '.hookSpecificOutput.permissionDecisionReason')
  [[ "$reason" == *"All model tiers exhausted for requested tier 'opus'."* ]]
  [[ "$reason" == *"/model-routing-check"* ]]
}

@test "hook: AC17 cycle emits permissionDecision=deny with cycle message" {
  cat > "$MODEL_OVERRIDES_JSON" <<'EOF'
{ "tier_aliases": { "haiku": "sonnet", "sonnet": "haiku" } }
EOF
  local input
  input=$(_pretooluse_agent_input "haiku" "naming-review")
  run bash -c "echo '$input' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  local decision
  decision=$(echo "$output" | jq -r '.hookSpecificOutput.permissionDecision')
  [ "$decision" = "deny" ]
  local reason
  reason=$(echo "$output" | jq -r '.hookSpecificOutput.permissionDecisionReason')
  [[ "$reason" == *"Cycle detected in tier aliases:"* ]]
}

@test "hook: AC17 missing routing.json emits permissionDecision=deny" {
  export MODEL_ROUTING_JSON="$BATS_TMPDIR_CASE/missing.json"
  local input
  input=$(_pretooluse_agent_input "haiku" "naming-review")
  run bash -c "echo '$input' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  local decision
  decision=$(echo "$output" | jq -r '.hookSpecificOutput.permissionDecision')
  [ "$decision" = "deny" ]
  local reason
  reason=$(echo "$output" | jq -r '.hookSpecificOutput.permissionDecisionReason')
  [[ "$reason" == *"Model routing file missing:"* ]]
}

@test "hook: AC17 malformed overrides emits permissionDecision=deny" {
  echo '{not json' > "$MODEL_OVERRIDES_JSON"
  local input
  input=$(_pretooluse_agent_input "haiku" "naming-review")
  run bash -c "echo '$input' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  local decision
  decision=$(echo "$output" | jq -r '.hookSpecificOutput.permissionDecision')
  [ "$decision" = "deny" ]
  local reason
  reason=$(echo "$output" | jq -r '.hookSpecificOutput.permissionDecisionReason')
  [[ "$reason" == *"Override file is not valid JSON:"* ]]
}

# ---------------------------------------------------------------------------
# AC18 — settings.json registration
# ---------------------------------------------------------------------------

@test "AC18: settings.json registers agent-model-resolve.sh under PreToolUse Agent matcher" {
  [ -f "$SETTINGS_JSON" ]
  run jq -e '.hooks.PreToolUse[] | select(.matcher == "Agent") | .hooks[] | select(.command | contains("agent-model-resolve.sh"))' "$SETTINGS_JSON"
  [ "$status" -eq 0 ]
}
