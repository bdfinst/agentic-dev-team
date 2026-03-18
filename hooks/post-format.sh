#!/usr/bin/env bash
# post-format.sh — Claude Code PostToolUse hook
#
# Runs after Write and Edit tool calls. Auto-formats the changed file
# using the appropriate formatter for the detected language.
#
# Input:  JSON on stdin with tool_input.file_path
# Output: Message on stdout; always exit 0 (formatting is best-effort)
#
# This hook is language-aware. /setup generates a project-specific version
# with only the relevant branches, but this universal version handles all
# supported stacks.

set -uo pipefail

INPUT=$(cat)
FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)

# No file path — nothing to format
[ -z "$FILE" ] && exit 0

# File must exist
[ -f "$FILE" ] || exit 0

# Route to the appropriate formatter based on file extension
case "$FILE" in
  *.ts|*.tsx|*.js|*.jsx|*.mjs|*.cjs)
    if command -v npx &>/dev/null; then
      npx prettier --write "$FILE" 2>/dev/null || true
      npx eslint --fix "$FILE" 2>/dev/null || true
    fi
    ;;
  *.py)
    if command -v ruff &>/dev/null; then
      ruff format "$FILE" 2>/dev/null || true
      ruff check --fix "$FILE" 2>/dev/null || true
    elif command -v black &>/dev/null; then
      black "$FILE" 2>/dev/null || true
    fi
    ;;
  *.go)
    if command -v gofmt &>/dev/null; then
      gofmt -w "$FILE" 2>/dev/null || true
    fi
    ;;
  *.rs)
    if command -v rustfmt &>/dev/null; then
      rustfmt "$FILE" 2>/dev/null || true
    fi
    ;;
  *.rb)
    if command -v bundle &>/dev/null; then
      bundle exec rubocop -A "$FILE" 2>/dev/null || true
    fi
    ;;
  *.java)
    if command -v google-java-format &>/dev/null; then
      google-java-format -i "$FILE" 2>/dev/null || true
    fi
    ;;
  *.kt)
    if command -v ktlint &>/dev/null; then
      ktlint -F "$FILE" 2>/dev/null || true
    fi
    ;;
  *.cs)
    if command -v dotnet &>/dev/null; then
      dotnet format --include "$FILE" 2>/dev/null || true
    fi
    ;;
esac

exit 0
