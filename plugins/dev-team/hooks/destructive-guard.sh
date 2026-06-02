#!/usr/bin/env bash
# destructive-guard.sh — Claude Code PreToolUse hook
#
# Runs before Bash tool calls. Detects destructive commands and either warns
# (default) or blocks (when careful mode is active).
#
# Input:  JSON on stdin with tool_input.command
# Output: Message on stdout; exit 2 to block, exit 0 to allow/warn
# Config: hooks/destructive-commands.json, hooks/careful-state.json

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMMANDS_FILE="$SCRIPT_DIR/destructive-commands.json"
CAREFUL_FILE="$SCRIPT_DIR/careful-state.json"

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)

# No command extracted — pass through
[ -z "$COMMAND" ] && exit 0

LOWER_COMMAND=$(echo "$COMMAND" | tr '[:upper:]' '[:lower:]')

# ── Check careful mode ────────────────────────────────────────────────────────
CAREFUL_ACTIVE=false
if [ -f "$CAREFUL_FILE" ] && command -v jq &>/dev/null; then
  CAREFUL_ACTIVE=$(jq -r '.active // false' "$CAREFUL_FILE" 2>/dev/null || echo "false")
fi

# ── Load patterns from config, fall back to inline defaults ───────────────────
if [ -f "$COMMANDS_FILE" ] && command -v jq &>/dev/null; then
  FILE_PATTERNS=$(jq -r '.file_destruction[]' "$COMMANDS_FILE" 2>/dev/null || true)
  DB_PATTERNS=$(jq -r '.database_destruction[]' "$COMMANDS_FILE" 2>/dev/null || true)
  GIT_PATTERNS=$(jq -r '.git_destruction[]' "$COMMANDS_FILE" 2>/dev/null || true)
  PROCESS_PATTERNS=$(jq -r '.process_destruction[]' "$COMMANDS_FILE" 2>/dev/null || true)
  PERMISSION_PATTERNS=$(jq -r '.permission_escalation[]' "$COMMANDS_FILE" 2>/dev/null || true)
  SAFE_PATTERNS=$(jq -r '.safe_allowlist[]' "$COMMANDS_FILE" 2>/dev/null || true)
else
  FILE_PATTERNS="rm -rf
rm -r
rm -fr"
  DB_PATTERNS="drop table
drop database
truncate"
  GIT_PATTERNS="git push --force
git push -f
git reset --hard
git clean -f
git clean -fd
git checkout -- .
git branch -D"
  PROCESS_PATTERNS="kill -9
killall
pkill"
  PERMISSION_PATTERNS="chmod 777"
  SAFE_PATTERNS="rm -rf node_modules
rm -rf dist
rm -rf build
rm -rf .cache
rm -rf coverage
rm -rf tmp
rm -rf __pycache__"
fi

# ── Check if command matches a safe allowlist pattern ─────────────────────────
matches_safe() {
  local cmd="$1"
  while IFS= read -r pattern; do
    [ -z "$pattern" ] && continue
    case "$cmd" in
      *"$pattern"*) return 0 ;;
    esac
  done <<< "$SAFE_PATTERNS"
  return 1
}

# ── Check if command matches any destructive pattern ──────────────────────────
check_patterns() {
  local cmd="$1"
  local patterns="$2"
  local category="$3"
  while IFS= read -r pattern; do
    [ -z "$pattern" ] && continue
    case "$cmd" in
      *"$pattern"*)
        echo "$category: $pattern"
        return 0
        ;;
    esac
  done <<< "$patterns"
  return 1
}

# Skip if command matches safe allowlist
if matches_safe "$LOWER_COMMAND"; then
  exit 0
fi

# Check all pattern categories
MATCH=""
MATCH=$(check_patterns "$LOWER_COMMAND" "$FILE_PATTERNS" "File destruction") || true
[ -z "$MATCH" ] && MATCH=$(check_patterns "$LOWER_COMMAND" "$DB_PATTERNS" "Database destruction") || true
[ -z "$MATCH" ] && MATCH=$(check_patterns "$LOWER_COMMAND" "$GIT_PATTERNS" "Git destruction") || true
[ -z "$MATCH" ] && MATCH=$(check_patterns "$LOWER_COMMAND" "$PROCESS_PATTERNS" "Process destruction") || true
[ -z "$MATCH" ] && MATCH=$(check_patterns "$LOWER_COMMAND" "$PERMISSION_PATTERNS" "Permission escalation") || true

# No match — allow
[ -z "$MATCH" ] && exit 0

# ── Match found — warn or block ──────────────────────────────────────────────
if [ "$CAREFUL_ACTIVE" = "true" ]; then
  echo "BLOCKED: Destructive command detected ($MATCH)."
  echo "Command: $COMMAND"
  echo "Careful mode is active. This command has been blocked."
  echo "Use /careful off to disable careful mode, or confirm with the user."
  exit 2
else
  echo "CAUTION: Destructive command detected ($MATCH)."
  echo "Command: $COMMAND"
  echo "This action is hard to reverse. Confirm with the user before proceeding."
  exit 0
fi
