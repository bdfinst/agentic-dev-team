#!/usr/bin/env bash
# agent-dispatch-log.sh — auto-time every Agent tool dispatch.
#
# Registered as both PreToolUse and PostToolUse on the Agent tool.
# Writes two line types to memory/agent-dispatches.jsonl:
#
#   {"ts":"2026-04-22T12:00:00Z","epoch":1700000000,"event":"agent_start",
#    "agent_type":"codebase-recon","description":"...","session_pid":12345}
#   {"ts":"2026-04-22T12:00:45Z","epoch":1700000045,"event":"agent_end",
#    "agent_type":"codebase-recon","duration_seconds":45,"session_pid":12345}
#
# The exec-report-generator reads this log alongside
# memory/phase-timings-<slug>.jsonl. Correlation: agent dispatches that
# fall between the assessment run's phase-0 start and phase-5 end belong
# to that run. Dispatches outside that window are ignored for that run's
# report but remain in the log for audit.
#
# Mode is inferred from the HOOK_EVENT_NAME environment variable that
# Claude Code sets for hooks:
#   HOOK_EVENT_NAME=PreToolUse   -> record agent_start
#   HOOK_EVENT_NAME=PostToolUse  -> record agent_end
#
# Input:  JSON on stdin
# Output: always exit 0 (hook is observability-only; never blocks)

set -uo pipefail

INPUT=$(cat)

TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")
[ "$TOOL_NAME" != "Agent" ] && exit 0

EVENT="${HOOK_EVENT_NAME:-unknown}"

AGENT_TYPE=$(echo "$INPUT" | jq -r '.tool_input.subagent_type // "unknown"' 2>/dev/null || echo "unknown")
DESCRIPTION=$(echo "$INPUT" | jq -r '.tool_input.description // ""' 2>/dev/null | head -c 200)

LOG_DIR="$(pwd)/memory"
LOG_FILE="$LOG_DIR/agent-dispatches.jsonl"
mkdir -p "$LOG_DIR" 2>/dev/null || true

ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
epoch=$(date -u +%s)

case "$EVENT" in
  PreToolUse)
    printf '{"ts":"%s","epoch":%d,"event":"agent_start","agent_type":"%s","description":%s,"session_pid":%d}\n' \
      "$ts" "$epoch" "$AGENT_TYPE" "$(printf '%s' "$DESCRIPTION" | jq -Rs . 2>/dev/null || echo '""')" "$$" \
      >> "$LOG_FILE" 2>/dev/null || true
    ;;
  PostToolUse)
    # Recover start epoch for this agent/pid by reading the log backwards.
    start_epoch=""
    if [ -f "$LOG_FILE" ]; then
      # Find the most recent agent_start for this PID (any agent type;
      # different concurrent dispatches have different PIDs in practice).
      start_epoch=$(grep "\"event\":\"agent_start\",\"agent_type\":\"$AGENT_TYPE\"" "$LOG_FILE" 2>/dev/null \
        | grep "\"session_pid\":$$" | tail -1 \
        | sed -n 's/.*"epoch":\([0-9]*\).*/\1/p' || true)
      # Fallback: most recent agent_start for this agent type regardless of pid
      if [ -z "$start_epoch" ]; then
        start_epoch=$(grep "\"event\":\"agent_start\",\"agent_type\":\"$AGENT_TYPE\"" "$LOG_FILE" 2>/dev/null \
          | tail -1 | sed -n 's/.*"epoch":\([0-9]*\).*/\1/p' || true)
      fi
    fi
    if [ -n "$start_epoch" ]; then
      duration=$((epoch - start_epoch))
    else
      duration=0
    fi
    printf '{"ts":"%s","epoch":%d,"event":"agent_end","agent_type":"%s","duration_seconds":%d,"session_pid":%d}\n' \
      "$ts" "$epoch" "$AGENT_TYPE" "$duration" "$$" \
      >> "$LOG_FILE" 2>/dev/null || true
    ;;
esac

exit 0
