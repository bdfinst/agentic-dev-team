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
#   4. If tool_input.model is an explicit snapshot that a present ladder does
#      NOT contain, fall back to the session model (the model is unavailable
#      in this environment). With no ladder, or a snapshot the ladder has,
#      pass it through untouched.
#   5. Unreadable/unknown agent with no usable band/model → pass-through.
#
# The session model is never a ceiling: a high-effort agent maps to the top of
# the ladder even when the session started on a lower model.
#
# Bump logging is owned HERE (single site): the resolver no longer logs. A
# JSONL line is appended when the resolved model differs from the band's
# shipped default (a ladder override / upgrade / downgrade), always for a
# legacy-tier dispatch (a deprecation marker), and for a session-model
# fallback. A resolution equal to the default still rewrites the model but
# logs nothing. Per-dispatch resolution emits no user-visible message.
#
# Posture: fail-open on any parse/internal/resolver error → empty stdout,
# exit 0. A buggy hook (or a missing routing.json) must never block dispatch.

set -uo pipefail

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESOLVER="${HOOK_DIR}/lib/model-resolve.sh"

# Path seams (TEST-ONLY env overrides; default to plugin-relative paths).
_routing_json()       { echo "${MODEL_ROUTING_JSON:-${HOOK_DIR}/../knowledge/model-routing.json}"; }
_agents_dir()         { echo "${MODEL_AGENTS_DIR:-${HOOK_DIR}/../agents}"; }
_ladder_json()        { echo "${MODEL_LADDER_JSON:-.claude/model-ladder.json}"; }
_session_model_file() { echo "${SESSION_MODEL_FILE:-.claude/session-model}"; }
_bump_log()           { echo "${MODEL_BUMP_LOG:-.claude/metrics/model-routing.log}"; }

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
# _ladder_is_valid / _snapshot_in_ladder — ladder presence + membership.
# ---------------------------------------------------------------------------
_ladder_is_valid() {
  local l
  l="$(_ladder_json)"
  [[ -e "$l" ]] || return 1
  jq -e 'type == "array" and length > 0 and all(.[]; type == "string")' \
    "$l" >/dev/null 2>&1
}

_snapshot_in_ladder() {
  local snap="$1" l
  l="$(_ladder_json)"
  _ladder_is_valid || return 1
  jq -e --arg s "$snap" 'index($s) != null' "$l" >/dev/null 2>&1
}

# ---------------------------------------------------------------------------
# _session_model — the persisted session model, or "" if none.
# ---------------------------------------------------------------------------
_session_model() {
  local f
  f="$(_session_model_file)"
  if [[ -f "$f" ]]; then
    head -n 1 "$f"
  else
    echo ""
  fi
}

# ---------------------------------------------------------------------------
# _log_bump — append exactly one JSONL line to the bump log.
# Args: band served reason caller session
# ---------------------------------------------------------------------------
_log_bump() {
  local band="$1" served="$2" reason="$3" caller="$4" session="${5:-}"
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
    --arg session "$session" \
    '{ts: $ts, band: $band, served: $served, reason: $reason, caller: $caller, session: $session}' \
    >> "$log"
}

# ---------------------------------------------------------------------------
# _emit_rewrite — print the updatedInput envelope rewriting tool_input.model.
# Args: input new_model
# ---------------------------------------------------------------------------
_emit_rewrite() {
  echo "$1" | jq -c --arg new_model "$2" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      updatedInput: (.tool_input | .model = $new_model)
    }
  }'
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

  local band="" reason="" explicit_snapshot=""
  if [[ -n "$effort" ]]; then
    band="$(_normalize_band "$effort")"
    reason="effort"
  elif [[ -n "$requested_model" ]]; then
    band="$(_normalize_band "$requested_model")"
    if [[ -n "$band" ]]; then
      # Legacy fallback: the agent still declares a tier in tool_input.model.
      reason="legacy-tier"
    else
      # An explicit snapshot ID (neither band nor tier).
      explicit_snapshot="$requested_model"
    fi
  fi

  local session
  session="$(_session_model)"

  # No band: either an explicit snapshot or an unknown/modelless dispatch.
  if [[ -z "$band" ]]; then
    # Explicit out-of-ladder snapshot → fall back to the session model (the
    # requested model is not available in this environment). With no ladder,
    # or a snapshot the ladder contains, leave it untouched.
    if [[ -n "$explicit_snapshot" ]] && _ladder_is_valid \
       && ! _snapshot_in_ladder "$explicit_snapshot" && [[ -n "$session" ]]; then
      _log_bump "" "$session" "session-fallback" "$agent_name" "$session"
      _emit_rewrite "$input" "$session"
      return 0
    fi
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
  # differs from the band's shipped default (an upgrade or a downgrade).
  local routing default
  routing="$(_routing_json)"
  default=""
  if [[ -f "$routing" ]]; then
    default=$(jq -r --arg b "$band" '.[$b] // empty' "$routing" 2>/dev/null)
  fi
  if [[ "$reason" == "legacy-tier" || "$resolved" != "$default" ]]; then
    _log_bump "$band" "$resolved" "$reason" "$agent_name" "$session"
  fi

  # Always rewrite tool_input.model so the harness dispatches on a concrete
  # model — effort agents declare no model: of their own. The session model is
  # never a ceiling: the resolved band model wins even if it is more capable.
  _emit_rewrite "$input" "$resolved"
}

main
