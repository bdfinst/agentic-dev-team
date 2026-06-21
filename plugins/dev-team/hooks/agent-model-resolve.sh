#!/usr/bin/env bash
# agent-model-resolve.sh — PreToolUse hook on the "Agent" matcher.
#
# Resolves an agent's effort band to a concrete model before any sub-agent
# dispatch reaches the harness, then rewrites tool_input.model so the harness
# dispatches on it. Reads PreToolUse-shaped JSON from stdin and emits one of:
#
#   - rewrite:        {"hookSpecificOutput":{"hookEventName":"PreToolUse",
#                       "updatedInput": {...tool_input with model set...}}}
#   - pass-through:   {}
#
# Resolution order for an Agent dispatch:
#   1. Strip any "<plugin>:" prefix from subagent_type.
#   2. Read the effort band from agents/<name>.md frontmatter and resolve it
#      via lib/model-resolve.sh (default map or ladder). ALWAYS rewrite the
#      model — effort agents declare no model: of their own.
#   3. If the agent declares no effort band, fall back to a legacy
#      tool_input.model tier (haiku|sonnet|opus → band) and rewrite, marking
#      the dispatch as legacy in the bump log.
#   4. Unreadable/unknown agent with no usable band → pass-through.
#
# Bump logging is owned HERE (single site): the resolver no longer logs. A
# JSONL line is appended when the resolved model differs from the band's
# shipped default (a ladder override / upgrade / downgrade), and always for a
# legacy-tier dispatch (a deprecation marker). A resolution equal to the
# default still rewrites the model but logs nothing.
#
# Posture: fail-open on any parse/internal/resolver error → empty stdout,
# exit 0. A buggy hook (or a missing routing.json) must never block dispatch.

set -uo pipefail

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESOLVER="${HOOK_DIR}/lib/model-resolve.sh"

# Path seams (TEST-ONLY env overrides; default to plugin-relative paths).
_routing_json() { echo "${MODEL_ROUTING_JSON:-${HOOK_DIR}/../knowledge/model-routing.json}"; }
_agents_dir()   { echo "${MODEL_AGENTS_DIR:-${HOOK_DIR}/../agents}"; }
_bump_log()     { echo "${MODEL_BUMP_LOG:-.claude/metrics/model-routing.log}"; }

# ---------------------------------------------------------------------------
# _read_effort — extract the effort band from an agent file's YAML
# frontmatter. Echoes "" when the file is unreadable or declares no effort.
# ---------------------------------------------------------------------------
_read_effort() {
  local f="$1"
  [[ -r "$f" ]] || { echo ""; return 0; }
  awk '
    NR == 1 && $0 == "---" { infm = 1; next }
    infm && $0 == "---" { exit }
    infm && /^effort:[[:space:]]*/ {
      val = $0
      sub(/^effort:[[:space:]]*/, "", val)
      gsub(/["'"'"'[:space:]]/, "", val)
      print val
      exit
    }
  ' "$f"
}

# ---------------------------------------------------------------------------
# _normalize_band — band or legacy tier → canonical band ("" if unknown).
# ---------------------------------------------------------------------------
_normalize_band() {
  case "$1" in
    low|haiku)     echo "low" ;;
    medium|sonnet) echo "medium" ;;
    high|opus)     echo "high" ;;
    *)             echo "" ;;
  esac
}

# ---------------------------------------------------------------------------
# _log_bump — append exactly one JSONL line to the bump log.
# ---------------------------------------------------------------------------
_log_bump() {
  local band="$1" served="$2" reason="$3" caller="$4"
  local log
  log="$(_bump_log)"
  mkdir -p "$(dirname "$log")"
  local ts
  ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  jq -nc \
    --arg ts "$ts" \
    --arg band "$band" \
    --arg served "$served" \
    --arg reason "$reason" \
    --arg caller "$caller" \
    '{ts: $ts, band: $band, served: $served, reason: $reason, caller: $caller}' \
    >> "$log"
}

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

  # Strip any "<plugin>:" prefix (dev-team:security-review → security-review).
  local agent_name="${subagent_type#*:}"
  local agent_file
  agent_file="$(_agents_dir)/${agent_name}.md"

  local effort
  effort="$(_read_effort "$agent_file")"

  local band="" reason=""
  if [[ -n "$effort" ]]; then
    band="$(_normalize_band "$effort")"
    reason="effort"
  elif [[ -n "$requested_model" ]]; then
    # Legacy fallback: the agent still declares a tier in tool_input.model.
    band="$(_normalize_band "$requested_model")"
    reason="legacy-tier"
  fi

  # Unknown/unreadable agent with no usable band → pass-through.
  if [[ -z "$band" ]]; then
    echo '{}'
    return 0
  fi

  local resolved status
  resolved=$(bash "$RESOLVER" "$band" --caller "$agent_name" 2>/dev/null)
  status=$?

  # Fail-open on any resolver error (including exit 4, missing routing.json).
  if [[ $status -ne 0 || -z "$resolved" ]]; then
    echo '{}'
    return 0
  fi

  # Bump logging (single site). Legacy-tier dispatches always log a
  # deprecation marker; effort dispatches log only when the resolved model
  # differs from the band's shipped default.
  local routing default
  routing="$(_routing_json)"
  default=""
  if [[ -f "$routing" ]]; then
    default=$(jq -r --arg b "$band" '.[$b] // empty' "$routing" 2>/dev/null)
  fi
  if [[ "$reason" == "legacy-tier" || "$resolved" != "$default" ]]; then
    _log_bump "$band" "$resolved" "$reason" "$agent_name"
  fi

  # Always rewrite tool_input.model so the harness dispatches on a concrete
  # model — effort agents declare no model: of their own.
  echo "$input" | jq -c \
    --arg new_model "$resolved" \
    '{
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        updatedInput: (.tool_input | .model = $new_model)
      }
    }'
}

main
