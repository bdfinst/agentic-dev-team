#!/usr/bin/env bash
# pre-tool-guard.sh — Claude Code PreToolUse hook
#
# Runs before Write and Edit tool calls. Blocks writes to sensitive paths
# (credentials, secrets, keys). Warns on writes to protected config files.
#
# Input:  JSON on stdin with tool_input.file_path or tool_input.path
# Output: Message on stdout; exit 2 to block, exit 0 to allow
# Config: .claude/hooks/guards.json

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GUARDS_FILE="$SCRIPT_DIR/guards.json"

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.path // empty' 2>/dev/null || true)

# No file path extracted — pass through
[ -z "$FILE_PATH" ] && exit 0

FILENAME=$(basename "$FILE_PATH")
LOWER_FILENAME=$(echo "$FILENAME" | tr '[:upper:]' '[:lower:]')
LOWER_PATH=$(echo "$FILE_PATH" | tr '[:upper:]' '[:lower:]')

# ── Helper: test subject against a newline-delimited list of glob patterns ────
matches_any() {
  local subject="$1"
  local patterns="$2"
  while IFS= read -r pattern; do
    [ -z "$pattern" ] && continue
    # shellcheck disable=SC2254
    case "$subject" in
      $pattern) return 0 ;;
    esac
  done <<< "$patterns"
  return 1
}

# ── Load guards from config, fall back to inline defaults ────────────────────
if [ -f "$GUARDS_FILE" ] && command -v jq &>/dev/null; then
  BLOCKED_PATTERNS=$(jq -r '.blocked_paths[]' "$GUARDS_FILE" 2>/dev/null || true)
  WARN_PATTERNS=$(jq -r '.warn_paths[]' "$GUARDS_FILE" 2>/dev/null || true)
else
  BLOCKED_PATTERNS=".env
.env.*
*.pem
*.key
*.p12
*.pfx
*credential*
*secret*
*.token"
  WARN_PATTERNS=".claude/settings.json
.claude/claude.md"
fi

# ── Block: sensitive credential / key paths ───────────────────────────────────
if matches_any "$LOWER_FILENAME" "$BLOCKED_PATTERNS" || \
   matches_any "$LOWER_PATH" "$BLOCKED_PATTERNS"; then
  echo "BLOCKED: Write to '$FILE_PATH' is not allowed."
  echo "This path matches a sensitive-file pattern in .claude/hooks/guards.json."
  echo "If this write is intentional, confirm with the user before proceeding."
  exit 2
fi

# ── Warn: protected config files ─────────────────────────────────────────────
if matches_any "$LOWER_PATH" "$WARN_PATTERNS"; then
  echo "WARNING: '$FILE_PATH' is a protected configuration file."
  echo "Verify this change is intentional before writing."
fi

exit 0
