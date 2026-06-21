#!/usr/bin/env bash
# session-model-banner.sh — Claude Code SessionStart hook (the single one that
# owns model routing). It:
#   1. Captures the session model from the SessionStart payload and persists
#      it to .claude/session-model so per-dispatch resolution can fall back to
#      it (Slice 3).
#   2. Announces the effort band→model routing table on stderr, flagging any
#      band whose model is more capable than the session model.
#
# Replaces the retired overrides-banner.sh (one SessionStart hook, not two).
#
# Input:  SessionStart JSON on stdin (hook_event_name, cwd, model, ...).
# Output: Banner text on stderr. Exit 0 always — a buggy banner hook must
#         never block a session.
#
# Env seams (TEST-ONLY):
#   MODEL_ROUTING_JSON   defaults to <plugin>/knowledge/model-routing.json
#   MODEL_LADDER_JSON    defaults to .claude/model-ladder.json
#   SESSION_MODEL_FILE   defaults to .claude/session-model

set -uo pipefail

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

_session_model_file() { echo "${SESSION_MODEL_FILE:-.claude/session-model}"; }

main() {
  local input
  input=$(cat)

  # Fail-open on malformed input.
  if ! echo "$input" | jq -e . >/dev/null 2>&1; then
    return 0
  fi

  # Extract the session model (string, or object with .id).
  local model
  model=$(echo "$input" | jq -r '(.model // empty) as $m
    | if ($m | type) == "object" then ($m.id // empty) else $m end' 2>/dev/null)

  local file
  file="$(_session_model_file)"
  if [[ -n "$model" ]]; then
    mkdir -p "$(dirname "$file")"
    printf '%s\n' "$model" > "$file"
  fi

  return 0
}

main
