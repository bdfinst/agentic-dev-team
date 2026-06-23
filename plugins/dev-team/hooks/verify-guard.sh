#!/usr/bin/env bash
# verify-guard.sh — Claude Code PreToolUse hook
#
# Detects repeated identical verify invocations within a session and emits
# a convergence warning after THRESHOLD consecutive identical runs, nudging
# the agent to change approach rather than re-running the same failing command.
#
# Input:  JSON on stdin (hook_event_name, session_id, tool_input.command, cwd)
# Output: Warning on stdout; always exit 0 (advisory, never blocks)
# Threshold: DEV_TEAM_VERIFY_THRESHOLD (default 3)

set -uo pipefail

INPUT=$(cat)
command -v jq >/dev/null 2>&1 || exit 0

CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
[ -z "$CMD" ] && exit 0

# Only fire on verify-class commands (mirrors session_extract.py _VERIFY_RE)
if ! echo "$CMD" | grep -qE \
  '\b(npm (run )?(test|lint|build)|pytest|bats|eslint|tsc|go test|cargo (test|build)|mvn|gradle|make( |$)|vitest|jest|ruff|mypy|shellcheck)\b'; then
  exit 0
fi

SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)
CWD=$(echo "$INPUT" | jq -r '.cwd // empty' 2>/dev/null || true)
# Derive a stable key: prefer session_id, fall back to cwd hash
if [ -n "$SESSION_ID" ]; then
  STATE_KEY="$SESSION_ID"
else
  STATE_KEY=$(echo "${CWD:-$PWD}" | cksum | cut -d' ' -f1)
fi

STATE_DIR="${TMPDIR:-/tmp}/dev-team-verify-guard"
mkdir -p "$STATE_DIR"
STATE_FILE="$STATE_DIR/${STATE_KEY}.json"

# Normalize the command (collapse whitespace) for comparison
NORM_CMD=$(echo "$CMD" | tr -s '[:space:]' ' ' | sed 's/^ //;s/ $//')
NORM_HASH=$(echo "$NORM_CMD" | cksum | cut -d' ' -f1)

THRESHOLD="${DEV_TEAM_VERIFY_THRESHOLD:-3}"

# Read current state
prev_hash=""
count=0
if [ -f "$STATE_FILE" ] && command -v jq >/dev/null 2>&1; then
  prev_hash=$(jq -r '.hash // empty' "$STATE_FILE" 2>/dev/null || true)
  count=$(jq -r '.count // 0' "$STATE_FILE" 2>/dev/null || echo 0)
fi

# Update count: increment if same command, reset if different
if [ "$NORM_HASH" = "$prev_hash" ]; then
  count=$((count + 1))
else
  count=1
fi

# Write updated state
jq -nc --arg h "$NORM_HASH" --argjson c "$count" '{"hash":$h,"count":$c}' \
  > "$STATE_FILE" 2>/dev/null || true

# Warn if threshold exceeded
if [ "$count" -ge "$THRESHOLD" ]; then
  echo "verify-guard: This verify command has run ${count} consecutive times without a code change."
  echo "  If the tests are still failing, change the code rather than re-running the same command."
  echo "  To suppress this warning, set DEV_TEAM_VERIFY_THRESHOLD=0."
fi

exit 0
