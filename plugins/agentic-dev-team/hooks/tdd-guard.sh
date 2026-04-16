#!/usr/bin/env bash
# TDD Guard Hook — PostToolUse advisory for Write/Edit
# Tracks RED-GREEN-REFACTOR state and warns when implementation code
# is written without a preceding test file edit in the same session.
#
# State is tracked in a temp file per session. The hook detects whether
# the current edit is a test file or implementation file, and warns if
# implementation is edited without a recent test edit.

set -euo pipefail

# Read tool input from stdin
INPUT=$(cat)

# Extract the file path
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.path // .file_path // .path // empty' 2>/dev/null || true)

[ -n "$FILE_PATH" ] || exit 0
[ -f "$FILE_PATH" ] || exit 0

# Only check source code files (not config, docs, etc.)
case "$FILE_PATH" in
  *.ts|*.tsx|*.js|*.jsx|*.py|*.go|*.rs|*.java|*.cs|*.svelte|*.vue) ;;
  *) exit 0 ;;
esac

# Skip files in node_modules, dist, build, etc.
case "$FILE_PATH" in
  */node_modules/*|*/dist/*|*/build/*|*/.next/*|*/coverage/*) exit 0 ;;
esac

# --- Classify file as test or implementation ---

is_test_file() {
  local f="$1"
  case "$f" in
    *.test.*|*.spec.*|*_test.*|*_spec.*) return 0 ;;
    */test/*|*/tests/*|*/__tests__/*|*/spec/*) return 0 ;;
    *.feature) return 0 ;;
  esac
  # Check for test content patterns (jest, vitest, pytest, go test, etc.)
  if head -30 "$f" 2>/dev/null | grep -qE '(describe\(|it\(|test\(|expect\(|assert[A-Z]|def test_|func Test|#\[test\]|#\[cfg\(test\)\]|\[Fact\]|\[Theory\])'; then
    return 0
  fi
  return 1
}

# --- State tracking ---
# Use a project-scoped temp file. The working directory hash identifies the session scope.
STATE_DIR="${TMPDIR:-${TEMP:-/tmp}}/tdd-guard"
mkdir -p "$STATE_DIR"
PROJECT_HASH=$(echo "$PWD" | md5sum 2>/dev/null | cut -c1-12 || echo "$PWD" | md5 -q 2>/dev/null | cut -c1-12 || echo "default")
STATE_FILE="$STATE_DIR/session-$PROJECT_HASH"

# Clean up stale state files older than 4 hours
find "$STATE_DIR" -name "session-*" -mmin +240 -delete 2>/dev/null || true

# Read current state
LAST_TEST_EDIT=""
LAST_TEST_TIME=0
if [ -f "$STATE_FILE" ]; then
  LAST_TEST_EDIT=$(head -1 "$STATE_FILE" 2>/dev/null || true)
  LAST_TEST_TIME=$(tail -1 "$STATE_FILE" 2>/dev/null || echo "0")
fi

NOW=$(date +%s)

if is_test_file "$FILE_PATH"; then
  # Record this test edit
  printf "%s\n%s\n" "$FILE_PATH" "$NOW" > "$STATE_FILE"
  exit 0
fi

# --- Implementation file edited: check TDD state ---

# Grace period: if a test was edited within the last 5 minutes, allow it
ELAPSED=$((NOW - LAST_TEST_TIME))
if [ "$ELAPSED" -lt 300 ] && [ -n "$LAST_TEST_EDIT" ]; then
  # Test was recently edited — this is likely the GREEN phase
  exit 0
fi

# No recent test edit — warn
BASENAME=$(basename "$FILE_PATH")
printf "\n"
printf "  TDD: Implementation file edited without a recent test edit.\n"
printf "  File: %s\n" "$BASENAME"
printf "  Write a failing test FIRST, then implement. RED before GREEN.\n"
printf "  If this is a refactor with passing tests, run the test suite to confirm.\n"

exit 0
