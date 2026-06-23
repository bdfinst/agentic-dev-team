#!/usr/bin/env bash
# bash-retry-guard.sh — Claude Code PreToolUse hook
#
# Detects repeated identical Bash commands within a session. After
# THRESHOLD consecutive identical commands, nudges the agent to vary
# its approach rather than re-running the same failing command.
#
# Input:  JSON on stdin (session_id, tool_input.command, cwd)
# Output: Warning on stdout; always exit 0 (advisory, never blocks)
# Threshold: DEV_TEAM_BASH_RETRY_THRESHOLD (default 3)

set -uo pipefail

INPUT=$(cat)
command -v jq >/dev/null 2>&1 || exit 0

CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
[ -z "$CMD" ] && exit 0

# Exclude verify commands (verify-guard handles those)
if echo "$CMD" | grep -qE \
  '\b(npm (run )?(test|lint|build)|pytest|bats|eslint|tsc|go test|cargo (test|build)|mvn|gradle|make( |$)|vitest|jest|ruff|mypy|shellcheck)\b'; then
  exit 0
fi

# Exclude trivially short/read-only commands — they retry harmlessly
TRIMMED=$(echo "$CMD" | tr -s '[:space:]' ' ' | sed 's/^ //;s/ $//')
case "$TRIMMED" in
  ls|ls\ *|pwd|echo\ *|cat\ *|head\ *|tail\ *|grep\ *) exit 0 ;;
esac

SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)
CWD=$(echo "$INPUT" | jq -r '.cwd // empty' 2>/dev/null || true)
if [ -n "$SESSION_ID" ]; then
  STATE_KEY="$SESSION_ID"
else
  STATE_KEY=$(echo "${CWD:-$PWD}" | cksum | cut -d' ' -f1)
fi

STATE_DIR="${TMPDIR:-/tmp}/dev-team-bash-retry"
mkdir -p "$STATE_DIR"
STATE_FILE="$STATE_DIR/${STATE_KEY}.json"

NORM_HASH=$(echo "$TRIMMED" | cksum | cut -d' ' -f1)
THRESHOLD="${DEV_TEAM_BASH_RETRY_THRESHOLD:-3}"

prev_hash=""
count=0
if [ -f "$STATE_FILE" ]; then
  prev_hash=$(jq -r '.hash // empty' "$STATE_FILE" 2>/dev/null || true)
  count=$(jq -r '.count // 0' "$STATE_FILE" 2>/dev/null || echo 0)
fi

if [ "$NORM_HASH" = "$prev_hash" ]; then
  count=$((count + 1))
else
  count=1
fi

jq -nc --arg h "$NORM_HASH" --argjson c "$count" '{"hash":$h,"count":$c}' \
  > "$STATE_FILE" 2>/dev/null || true

if [ "$count" -ge "$THRESHOLD" ]; then
  echo "bash-retry-guard: This command has run ${count} consecutive times."
  echo "  If it keeps failing, investigate the root cause rather than retrying."
  echo "  Set DEV_TEAM_BASH_RETRY_THRESHOLD=0 to disable this warning."
fi

exit 0
