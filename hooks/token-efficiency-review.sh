#!/usr/bin/env bash
# Token Efficiency Hook — PostToolUse advisory for Write/Edit
# Checks file length, CLAUDE.md length, and function length.
# Full analysis is handled by the token-efficiency-review agent.

set -euo pipefail

# Read tool input from stdin
INPUT=$(cat)

# Extract the file path from the tool input (using jq for robust JSON parsing)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.path // .file_path // .path // empty' 2>/dev/null || true)

# Skip if file doesn't exist
[ -f "$FILE_PATH" ] || exit 0

WARNINGS=""

# Check CLAUDE.md length
BASENAME=$(basename "$FILE_PATH")
if [ "$BASENAME" = "CLAUDE.md" ] || [ "$BASENAME" = "claude.md" ]; then
  CHAR_COUNT=$(wc -c < "$FILE_PATH" | tr -d ' ')
  if [ "$CHAR_COUNT" -gt 5000 ]; then
    WARNINGS="${WARNINGS}
Token: CLAUDE.md is ${CHAR_COUNT} chars (limit: 5000). Move detailed examples to docs/ or skills."
  fi
fi

# Check file length (for source files)
case "$FILE_PATH" in
  *.js|*.ts|*.jsx|*.tsx|*.py|*.rb|*.go|*.rs|*.java|*.cs)
    LINE_COUNT=$(wc -l < "$FILE_PATH" | tr -d ' ')
    if [ "$LINE_COUNT" -gt 500 ]; then
      WARNINGS="${WARNINGS}
Token: File is ${LINE_COUNT} lines (limit: 500). Large files require more context tokens — consider splitting."
    fi

    # Check for long functions (basic heuristic: count lines between function declarations)
    # Look for functions longer than 50 lines
    LONG_FUNCS=$(awk '
      /^[[:space:]]*(async[[:space:]]+)?function[[:space:]]+[a-zA-Z_]/ ||
      /^[[:space:]]*(const|let|var)[[:space:]]+[a-zA-Z_]+[[:space:]]*=[[:space:]]*(async[[:space:]]+)?\(/ ||
      /^[[:space:]]+[a-zA-Z_]+[[:space:]]*\([^)]*\)[[:space:]]*\{/ {
        if (func_start > 0 && NR - func_start > 50) {
          print "  Line " func_start ": " func_name " (" NR - func_start " lines)"
        }
        func_start = NR
        func_name = $0
        sub(/^[[:space:]]+/, "", func_name)
        sub(/[({].*/, "", func_name)
      }
      END {
        if (func_start > 0 && NR - func_start > 50) {
          print "  Line " func_start ": " func_name " (" NR - func_start " lines)"
        }
      }
    ' "$FILE_PATH" 2>/dev/null || true)

    if [ -n "$LONG_FUNCS" ]; then
      WARNINGS="${WARNINGS}
Token: Long functions detected (limit: 50 lines). Split into smaller units:
${LONG_FUNCS}"
    fi
    ;;
esac

if [ -n "$WARNINGS" ]; then
  echo "$WARNINGS"
fi

exit 0
