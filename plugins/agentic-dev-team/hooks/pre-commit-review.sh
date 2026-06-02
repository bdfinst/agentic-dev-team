#!/usr/bin/env bash
#
# pre-commit-review.sh — PreToolUse hook that gates git commits on code review
#
# Blocks git commit (exit 2) unless a .review-passed file exists with a hash
# matching the currently staged files. The /code-review command auto-scopes
# to uncommitted changes and writes this file when review passes.
#
# Non-commit Bash commands pass through immediately (exit 0).
# git commit --no-verify is allowed through (standard bypass).
#
# Input: JSON on stdin with tool_input.command
# Exit 0: Allow the tool call
# Exit 2: Block the tool call (feedback returned to Claude)

set -uo pipefail

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/pre-commit-detect.sh
source "${HOOK_DIR}/lib/pre-commit-detect.sh"

# Read the tool input from stdin
INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // ""' 2>/dev/null)

# Fast exit for non-commit commands or --no-verify bypass
if ! _is_git_commit_invocation "$COMMAND"; then
  exit 0
fi

# Check for staged files
STAGED=$(git diff --cached --name-only 2>/dev/null)
if [ -z "$STAGED" ]; then
  exit 0
fi

# Compute hash of staged file paths
HASH=$(echo "$STAGED" | sort | shasum -a 256 2>/dev/null || echo "$STAGED" | sort | sha256sum 2>/dev/null)
HASH=$(echo "$HASH" | cut -d' ' -f1)

# Check for .review-passed gate file
GATE_FILE=".review-passed"
if [ -f "$GATE_FILE" ]; then
  STORED_HASH=$(cat "$GATE_FILE" 2>/dev/null)
  if [ "$HASH" = "$STORED_HASH" ]; then
    # Review passed for these exact files — allow commit and clean up
    rm -f "$GATE_FILE"
    exit 0
  fi
fi

# Block the commit
printf "BLOCKED: Code review required before committing.\n"
printf "\n"
printf "Run /code-review to review staged files.\n"
printf "If review passes, the commit will be allowed on the next attempt.\n"
printf "\n"
printf "To bypass: use git commit --no-verify\n"
exit 2
