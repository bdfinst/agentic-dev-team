#!/usr/bin/env bash
# session-learning-trigger.sh — SessionStop hook for the closed learning loop.
#
# Counts sessions and dispatches background session-analysis at threshold.
#
# CONSENT: Off by default. Set DEV_TEAM_AUTO_REVIEW=on to enable.
# THRESHOLD: DEV_TEAM_AUTO_REVIEW_THRESHOLD (default 5) sessions before dispatch.
# STATE: counter persisted in <cwd>/metrics/learning-loop-state.json.
#
# Posture: fail-open. Any I/O error exits 0 without crashing.

set -uo pipefail

# --- Consent gate -----------------------------------------------------------
[ "${DEV_TEAM_AUTO_REVIEW:-}" = "on" ] || exit 0

command -v jq >/dev/null 2>&1 || exit 0

INPUT=$(cat)
echo "$INPUT" | jq -e . >/dev/null 2>&1 || exit 0

cwd=$(echo "$INPUT" | jq -r '.cwd // empty')
[ -n "$cwd" ] && [ -d "$cwd" ] || cwd="$PWD"

SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')

THRESHOLD="${DEV_TEAM_AUTO_REVIEW_THRESHOLD:-5}"
STATE_FILE="${cwd}/metrics/learning-loop-state.json"
HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Read state (with corruption recovery) ----------------------------------
counter=0
if [ -f "$STATE_FILE" ]; then
  if ! counter=$(jq -r '.counter // empty' "$STATE_FILE" 2>/dev/null) || \
     ! [[ "$counter" =~ ^[0-9]+$ ]]; then
    counter=0
  fi
fi

# --- Increment --------------------------------------------------------------
counter=$((counter + 1))

# --- Helpers ----------------------------------------------------------------
_write_state() {
  local c="$1"
  local dir
  dir="$(dirname "$STATE_FILE")"
  mkdir -p "$dir" 2>/dev/null || return 0
  local tmp
  tmp=$(mktemp "${dir}/.learning-loop-state-XXXXXX.json" 2>/dev/null) || return 0
  jq -nc --argjson c "$c" '{counter: $c}' > "$tmp" 2>/dev/null \
    || { rm -f "$tmp"; return 0; }
  mv "$tmp" "$STATE_FILE" 2>/dev/null || rm -f "$tmp"
}

_should_dispatch() {
  [ "$counter" -ge "$THRESHOLD" ]
}

_dispatch_background_analysis() {
  local session_extract="${HOOK_DIR}/../../scripts/session_extract.py"
  local pending="${cwd}/metrics/pending-review.jsonl"
  local session_id_args=()
  if [ -n "${SESSION_ID:-}" ]; then
    # --session-id shares the parent's prompt-cache prefix, reducing background API cost ~26%
    session_id_args=(--session-id "$SESSION_ID")
  fi
  (
    python3 "$session_extract" --since last >/dev/null 2>&1 || true
    local tmp_out
    if ! tmp_out=$(mktemp "${cwd}/metrics/.pending-XXXXXX.jsonl" 2>/dev/null); then
      return
    fi
    if claude "${session_id_args[@]}" --dangerously-skip-permissions \
       --print "Run the session-analysis agent and output each finding as a JSONL entry to stdout with fields: queued_at (ISO-8601 UTC now), source (session-learning-trigger), session_id, findings (array of objects with lever, evidence, target_artifact, proposed_change, route)" \
       >"$tmp_out" 2>/dev/null; then
      cat "$tmp_out" >> "$pending" 2>/dev/null || true
    fi
    rm -f "$tmp_out"
  ) &
}

# --- Dispatch or save -------------------------------------------------------
if _should_dispatch; then
  _write_state 0
  _dispatch_background_analysis
else
  _write_state "$counter"
fi

exit 0
