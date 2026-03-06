#!/usr/bin/env bash
#
# pre-commit-review.sh - Claude Code PreCommit hook (opt-in)
#
# Blocks commits when review agents report fail status.
# Only active when review-config.json has "blockOnFail": true.
#
# Input: JSON on stdin with tool_input (commit details)
# Output: Feedback on stdout
# Exit 0: Advisory (pass or blockOnFail not enabled)
# Exit 2: Block commit (blockOnFail enabled and agents returned fail)

set -uo pipefail

# Check if blockOnFail is enabled in review-config.json
CONFIG_FILE="review-config.json"
if [ ! -f "$CONFIG_FILE" ]; then
  exit 0
fi

BLOCK_ON_FAIL=$(jq -r '.blockOnFail // false' "$CONFIG_FILE" 2>/dev/null)
if [ "$BLOCK_ON_FAIL" != "true" ]; then
  exit 0
fi

# Get changed files
CHANGED_FILES=$(git diff --cached --name-only 2>/dev/null)
if [ -z "$CHANGED_FILES" ]; then
  exit 0
fi

# Count source files (exclude docs, configs, images)
SOURCE_COUNT=$(echo "$CHANGED_FILES" | grep -cE '\.(js|ts|jsx|tsx|py|rb|go|rs|java|c|cpp|h)$' || true)
if [ "$SOURCE_COUNT" -eq 0 ]; then
  exit 0
fi

printf "\n"
printf "  pre-commit-review: blockOnFail is enabled\n"
printf "  %s source file(s) staged for commit\n" "$SOURCE_COUNT"
printf "  Run /code-review --changed --json to check for blocking issues before committing.\n"
printf "  To bypass: set \"blockOnFail\": false in review-config.json\n"
printf "\n"

# Advisory exit — the actual blocking happens via the review skill integration.
# This hook warns the user; the /code-review --json output determines pass/fail.
exit 0
