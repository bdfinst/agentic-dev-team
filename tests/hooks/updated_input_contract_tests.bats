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
# a deterministic gate, not a tribal assumption. Under the effort model the
# hook emits one of exactly two shapes: a rewrite (with updatedInput) or a
# pass-through ({}). The legacy deny envelope is gone — a missing routing.json
# now fails open, never denies.

HOOK="$BATS_TEST_DIRNAME/../../plugins/dev-team/hooks/agent-model-resolve.sh"

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
  printf -- '---\nname: high-agent\neffort: high\n---\nbody\n' > "$BATS_TMPDIR_CASE/agents/high-agent.md"
  export MODEL_ROUTING_JSON="$BATS_TMPDIR_CASE/knowledge/model-routing.json"
  export MODEL_AGENTS_DIR="$BATS_TMPDIR_CASE/agents"
  export MODEL_LADDER_JSON="$BATS_TMPDIR_CASE/.claude/model-ladder.json"
  export MODEL_BUMP_LOG="$BATS_TMPDIR_CASE/.claude/metrics/model-routing.log"
}

teardown() {
  rm -rf "$BATS_TMPDIR_CASE"
  unset MODEL_ROUTING_JSON MODEL_AGENTS_DIR MODEL_LADDER_JSON MODEL_BUMP_LOG
}

_agent_input() {
  local subagent_type="${1:-high-agent}"
  jq -nc --arg s "$subagent_type" \
    '{tool_name:"Agent", tool_input:{subagent_type:$s, description:"test", prompt:"test"}}'
}

# --------------------------------------------------------------------------
# Contract shape — the rewrite envelope
# --------------------------------------------------------------------------

@test "contract: rewrite envelope's only top-level key is hookSpecificOutput" {
  run bash -c "echo '$(_agent_input)' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  local keys
  keys=$(echo "$output" | jq -rc 'keys')
  [ "$keys" = '["hookSpecificOutput"]' ]
}

@test "contract: hookSpecificOutput carries exactly hookEventName + updatedInput on a rewrite" {
  run bash -c "echo '$(_agent_input)' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  local keys
  keys=$(echo "$output" | jq -rc '.hookSpecificOutput | keys')
  [ "$keys" = '["hookEventName","updatedInput"]' ]
  [ "$(echo "$output" | jq -r '.hookSpecificOutput.hookEventName')" = "PreToolUse" ]
}

@test "contract: updatedInput preserves every tool_input field and sets model" {
  local input
  input=$(_agent_input)
  run bash -c "echo '$input' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  # The resolved model is set.
  [ "$(echo "$output" | jq -r '.hookSpecificOutput.updatedInput.model')" = "claude-opus-4-8" ]
  # Every non-model field of the original tool_input is byte-identical.
  local non_model_in non_model_out
  non_model_in=$(echo "$input" | jq -Sc '.tool_input | del(.model)')
  non_model_out=$(echo "$output" | jq -Sc '.hookSpecificOutput.updatedInput | del(.model)')
  [ "$non_model_in" = "$non_model_out" ]
  # updatedInput = original keys ∪ {model}.
  local out_keys
  out_keys=$(echo "$output" | jq -rc '.hookSpecificOutput.updatedInput | keys')
  [ "$out_keys" = '["description","model","prompt","subagent_type"]' ]
}

# --------------------------------------------------------------------------
# Harness-change tripwire: every output is one of the two sanctioned shapes
# (rewrite-with-updatedInput / pass-through {}); never a deny.
# --------------------------------------------------------------------------

@test "contract: rewrite case carries updatedInput, never permissionDecision" {
  run bash -c "echo '$(_agent_input)' | bash '$HOOK'"
  echo "$output" | jq -e '.hookSpecificOutput.updatedInput' >/dev/null
  echo "$output" | jq -e 'has("hookSpecificOutput") and (.hookSpecificOutput | has("permissionDecision") | not)' >/dev/null
}

@test "contract: unknown agent with no model yields exactly {}" {
  run bash -c "echo '$(_agent_input does-not-exist)' | bash '$HOOK'"
  [ "$output" = "{}" ]
}
