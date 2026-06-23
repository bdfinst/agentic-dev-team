#!/usr/bin/env bash
# session-model-banner.sh — Claude Code SessionStart hook (the single one that
# owns model routing). It:
#   1. Captures the session model from the SessionStart payload and persists
#      it to .claude/session-model so per-dispatch resolution can fall back to
#      it (Slice 3). When the payload carries no model, it reuses the last
#      persisted value if one exists.
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
RESOLVER="${HOOK_DIR}/lib/model-resolve.sh"

_routing_json()       { echo "${MODEL_ROUTING_JSON:-${HOOK_DIR}/../knowledge/model-routing.json}"; }
_ladder_json()        { echo "${MODEL_LADDER_JSON:-.claude/model-ladder.json}"; }
_session_model_file() { echo "${SESSION_MODEL_FILE:-.claude/session-model}"; }

# ---------------------------------------------------------------------------
# _ladder_is_valid — true iff the ladder is a non-empty JSON array of strings.
# ---------------------------------------------------------------------------
_ladder_is_valid() {
  local l
  l="$(_ladder_json)"
  [[ -e "$l" ]] || return 1
  jq -e 'type == "array" and length > 0 and all(.[]; type == "string")' \
    "$l" >/dev/null 2>&1
}

# ---------------------------------------------------------------------------
# _ordered_models — the capability-ascending model list: the ladder when
# valid, else the shipped default map values (low→medium→high).
# ---------------------------------------------------------------------------
_ordered_models() {
  if _ladder_is_valid; then
    jq -r '.[]' "$(_ladder_json)"
  else
    jq -r '.low, .medium, .high' "$(_routing_json)"
  fi
}

# ---------------------------------------------------------------------------
# _rank — 1-based position of a model in the ordered list; 0 if not present.
# Args: target ordered_list_text
# ---------------------------------------------------------------------------
_rank() {
  local target="$1" list="$2" n=0 line
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    n=$((n + 1))
    if [[ "$line" == "$target" ]]; then
      echo "$n"
      return 0
    fi
  done <<< "$list"
  echo 0
}

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

  # The payload is untrusted. A model ID is a constrained token; reject anything
  # else so an arbitrary string is never persisted and later served as a model.
  if [[ -n "$model" && ! "$model" =~ ^[A-Za-z0-9._-]+$ ]]; then
    model=""
  fi

  local file
  file="$(_session_model_file)"

  # Capture: persist a fresh model. Reuse: fall back to the last persisted
  # value when the payload carries none.
  local session_model="" session_known=0 reused=0
  if [[ -n "$model" ]]; then
    mkdir -p "$(dirname "$file")"
    printf '%s\n' "$model" > "$file"
    session_model="$model"
    session_known=1
  elif [[ -f "$file" ]]; then
    session_model="$(cat "$file")"
    [[ -n "$session_model" ]] && { session_known=1; reused=1; }
  fi

  local cwd
  cwd=$(echo "$input" | jq -r '.cwd // empty' 2>/dev/null)
  [[ -n "$cwd" && -d "$cwd" ]] || cwd="$PWD"

  _render_banner "$session_model" "$session_known" "$reused" >&2
  _notify_pending_findings "$cwd"
  return 0
}

# ---------------------------------------------------------------------------
# _notify_pending_findings — emit a one-line notification when the
# pending-review queue has unreviewed entries.
# Args: cwd
# ---------------------------------------------------------------------------
_notify_pending_findings() {
  local cwd="$1"
  local queue="${PENDING_REVIEW_FILE:-${cwd}/metrics/pending-review.jsonl}"
  [[ -f "$queue" ]] || return 0
  local count
  count=$(jq -rs '[.[] | select(has("reviewed_at") | not)] | length' "$queue" 2>/dev/null) || return 0
  [[ "$count" -gt 0 ]] || return 0
  echo "📋 ${count} queued finding(s) from background analysis — run /session-review to review"
}

# ---------------------------------------------------------------------------
# _render_banner — print the band→model table and any flags/notes.
# Args: session_model session_known reused
# ---------------------------------------------------------------------------
_render_banner() {
  local session_model="$1" session_known="$2" reused="$3"

  local ordered n
  ordered="$(_ordered_models)"
  n=$(printf '%s\n' "$ordered" | grep -c .)

  # Single-model environment: collapse to one line.
  if [[ "$n" -eq 1 ]]; then
    local only
    only="$(printf '%s\n' "$ordered" | grep -m1 .)"
    echo "Model routing: all effort bands → ${only} (single-model environment)."
    return 0
  fi

  local session_rank=0
  if [[ "$session_known" -eq 1 ]]; then
    session_rank=$(_rank "$session_model" "$ordered")
  fi

  echo "Model routing (effort band → model):"
  local band m mrank flag
  for band in low medium high; do
    m=$(bash "$RESOLVER" "$band" 2>/dev/null)
    flag=""
    if [[ "$session_known" -eq 1 && "$session_rank" -gt 0 ]]; then
      mrank=$(_rank "$m" "$ordered")
      if [[ "$mrank" -gt "$session_rank" ]]; then
        flag="  ↑ above session model"
      fi
    fi
    printf '  %-7s → %s%s\n' "$band" "$m" "$flag"
  done

  if ! _ladder_is_valid; then
    echo "No ladder ($(_ladder_json)) — using shipped defaults; create it to override the band→model map."
  fi

  if [[ "$session_known" -ne 1 ]]; then
    echo "Session model unknown — upgrade flags and session fallback unavailable this session; effort routing still applies via the default map/ladder."
  elif [[ "$reused" -eq 1 ]]; then
    echo "(using last known session model: ${session_model})"
  fi
}

main
