#!/usr/bin/env bash
# agent-model-resolve.sh — PreToolUse hook on the "Agent" matcher.
#
# Enforces pre-dispatch tier → snapshot resolution before any sub-agent
# dispatch reaches the harness. Reads PreToolUse-shaped JSON from stdin,
# inspects tool_input.model, shells out to hooks/lib/model-resolve.sh, and
# emits one of:
#
#   - bump:           {"hookSpecificOutput":{"hookEventName":"PreToolUse",
#                       "updatedInput": {...tool_input with new model...}}}
#   - pass-through:   {}
#   - refusal:        {"hookSpecificOutput":{"hookEventName":"PreToolUse",
#                       "permissionDecision":"deny",
#                       "permissionDecisionReason":"<resolver stderr>"}}
#
# Pre-dispatch resolution is enforced HERE, not in orchestrator prose, so
# the LLM cannot bypass it. See ADR 00NN-pre-dispatch-resolution.md.
#
# Posture: fail-open on any parse/internal error → empty stdout, exit 0.
# A buggy hook must never block legitimate dispatch in the no-overrides
# case.

set -uo pipefail

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESOLVER="${HOOK_DIR}/lib/model-resolve.sh"

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
main() {
  local input
  input=$(cat)

  # Fail-open on malformed input.
  if ! echo "$input" | jq -e . >/dev/null 2>&1; then
    return 0
  fi

  local tool_name
  tool_name=$(echo "$input" | jq -r '.tool_name // empty')

  # Only act on Agent tool calls. Anything else is a no-op (empty output).
  if [[ "$tool_name" != "Agent" ]]; then
    return 0
  fi

  local requested_model subagent_type
  requested_model=$(echo "$input" | jq -r '.tool_input.model // empty')
  subagent_type=$(echo "$input" | jq -r '.tool_input.subagent_type // empty')

  # No model field, or it's already a snapshot ID (not a tier alias) →
  # pass-through.
  if [[ -z "$requested_model" ]]; then
    echo '{}'
    return 0
  fi
  case "$requested_model" in
    haiku|sonnet|opus) ;;
    *) echo '{}'; return 0 ;;
  esac

  # Resolve the tier. Capture stdout, stderr, and exit code.
  local resolver_stdout resolver_stderr resolver_status
  local stderr_file
  stderr_file=$(mktemp)
  resolver_stdout=$(bash "$RESOLVER" "$requested_model" --caller "$subagent_type" 2>"$stderr_file")
  resolver_status=$?
  resolver_stderr=$(cat "$stderr_file")
  rm -f "$stderr_file"

  case "$resolver_status" in
    0)
      # Resolved. Determine if a bump occurred by reading the bump log:
      # the resolver writes a JSONL line iff requested ≠ served. If no
      # bump line was appended for this invocation, this is a pass-through.
      # We detect this by checking whether the resolver produced the
      # routing.json default for the requested tier — if yes, pass-through.
      local routing_path
      routing_path="${MODEL_ROUTING_JSON:-${HOOK_DIR}/../knowledge/model-routing.json}"
      local default_snapshot=""
      if [[ -f "$routing_path" ]]; then
        default_snapshot=$(jq -r --arg t "$requested_model" '.[$t] // empty' "$routing_path" 2>/dev/null)
      fi
      if [[ -n "$default_snapshot" && "$resolver_stdout" == "$default_snapshot" ]]; then
        echo '{}'
        return 0
      fi
      # Bump: rewrite tool_input.model.
      echo "$input" | jq -c \
        --arg new_model "$resolver_stdout" \
        '{
          hookSpecificOutput: {
            hookEventName: "PreToolUse",
            updatedInput: (.tool_input | .model = $new_model)
          }
        }'
      ;;
    3|4|5)
      # Refusal. Embed resolver stderr as the deny reason.
      jq -nc \
        --arg reason "$resolver_stderr" \
        '{
          hookSpecificOutput: {
            hookEventName: "PreToolUse",
            permissionDecision: "deny",
            permissionDecisionReason: $reason
          }
        }'
      ;;
    *)
      # Any other exit code → fail-open.
      return 0
      ;;
  esac
}

main
