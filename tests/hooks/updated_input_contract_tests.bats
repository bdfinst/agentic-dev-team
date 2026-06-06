#!/usr/bin/env bats
# updatedInput PreToolUse rewrite-contract conformance test (issue #104).
#
# agent-model-resolve.sh depends on UNDOCUMENTED harness behavior: that a
# PreToolUse hook returning {"hookSpecificOutput":{"hookEventName":
# "PreToolUse","updatedInput":{...}}} causes the harness to dispatch the
# Agent with the rewritten tool_input (ADR-0004). If a harness change alters
# that contract, model routing breaks silently with nothing to catch it.
#
# This test pins the EXACT envelope shape the hook emits, so the contract is
# a deterministic gate, not a tribal assumption. It is intentionally narrow
# and toolchain-free (bash + jq only) so it runs in CI.

HOOK="$BATS_TEST_DIRNAME/../../plugins/dev-team/hooks/agent-model-resolve.sh"

setup() {
  BATS_TMPDIR_CASE="$(mktemp -d)"
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

_agent_input() {
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

# --------------------------------------------------------------------------
# Contract shape — the bump envelope
# --------------------------------------------------------------------------

@test "contract: bump envelope's only top-level key is hookSpecificOutput" {
  cat > "$MODEL_OVERRIDES_JSON" <<'EOF'
{ "tier_aliases": { "haiku": "sonnet" } }
EOF
  run bash -c "echo '$(_agent_input haiku)' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  local keys
  keys=$(echo "$output" | jq -rc 'keys')
  [ "$keys" = '["hookSpecificOutput"]' ]
}

@test "contract: hookSpecificOutput carries exactly hookEventName + updatedInput on a bump" {
  cat > "$MODEL_OVERRIDES_JSON" <<'EOF'
{ "tier_aliases": { "haiku": "sonnet" } }
EOF
  run bash -c "echo '$(_agent_input haiku)' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  local keys
  keys=$(echo "$output" | jq -rc '.hookSpecificOutput | keys')
  [ "$keys" = '["hookEventName","updatedInput"]' ]
  [ "$(echo "$output" | jq -r '.hookSpecificOutput.hookEventName')" = "PreToolUse" ]
}

@test "contract: updatedInput preserves the tool_input key-set exactly (only model value changes)" {
  cat > "$MODEL_OVERRIDES_JSON" <<'EOF'
{ "tier_aliases": { "haiku": "sonnet" } }
EOF
  local input
  input=$(_agent_input haiku)
  run bash -c "echo '$input' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  # Key-set of updatedInput must equal key-set of the original tool_input —
  # no fields dropped, none invented.
  local in_keys out_keys
  in_keys=$(echo "$input" | jq -rc '.tool_input | keys')
  out_keys=$(echo "$output" | jq -rc '.hookSpecificOutput.updatedInput | keys')
  [ "$in_keys" = "$out_keys" ]
  # Every non-model field is byte-identical; only model is rewritten.
  [ "$(echo "$output" | jq -r '.hookSpecificOutput.updatedInput.model')" = "claude-sonnet-4-6" ]
  local non_model_in non_model_out
  non_model_in=$(echo "$input" | jq -Sc '.tool_input | del(.model)')
  non_model_out=$(echo "$output" | jq -Sc '.hookSpecificOutput.updatedInput | del(.model)')
  [ "$non_model_in" = "$non_model_out" ]
}

@test "contract: 3-hop alias chain haiku->sonnet->opus resolves to the opus snapshot" {
  cat > "$MODEL_OVERRIDES_JSON" <<'EOF'
{ "tier_aliases": { "haiku": "sonnet", "sonnet": "opus" } }
EOF
  run bash -c "echo '$(_agent_input haiku)' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  [ "$(echo "$output" | jq -r '.hookSpecificOutput.updatedInput.model')" = "claude-opus-4-8" ]
}

# --------------------------------------------------------------------------
# Contract shape — the deny envelope (unresolvable states MUST deny)
# --------------------------------------------------------------------------

@test "contract: deny envelope carries exactly the three deny keys" {
  cat > "$MODEL_OVERRIDES_JSON" <<'EOF'
{ "tier_aliases": { "opus": "unavailable" } }
EOF
  run bash -c "echo '$(_agent_input opus security-review)' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  local keys
  keys=$(echo "$output" | jq -rc '.hookSpecificOutput | keys')
  [ "$keys" = '["hookEventName","permissionDecision","permissionDecisionReason"]' ]
  [ "$(echo "$output" | jq -r '.hookSpecificOutput.permissionDecision')" = "deny" ]
}

# --------------------------------------------------------------------------
# Harness-change tripwire: if the emitted envelope ever stops being one of
# the three sanctioned shapes (bump / pass-through {} / deny), fail loudly.
# --------------------------------------------------------------------------

@test "contract: every output is one of {bump-with-updatedInput, '{}', deny}" {
  # Pass-through case.
  run bash -c "echo '$(_agent_input haiku)' | bash '$HOOK'"
  [ "$output" = "{}" ]

  # Bump case carries updatedInput, never permissionDecision.
  cat > "$MODEL_OVERRIDES_JSON" <<'EOF'
{ "tier_aliases": { "haiku": "sonnet" } }
EOF
  run bash -c "echo '$(_agent_input haiku)' | bash '$HOOK'"
  echo "$output" | jq -e '.hookSpecificOutput.updatedInput' >/dev/null
  run bash -c "echo '$(_agent_input haiku)' | bash '$HOOK'"
  echo "$output" | jq -e 'has("hookSpecificOutput") and (.hookSpecificOutput | has("permissionDecision") | not)' >/dev/null
}
