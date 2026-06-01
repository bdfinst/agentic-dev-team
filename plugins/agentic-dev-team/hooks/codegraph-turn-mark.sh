#!/usr/bin/env bash
# codegraph-turn-mark.sh — Claude Code PostToolUse hook
#
# Fires after any mcp__codegraph__* tool call completes. Writes a sentinel
# at ${CLAUDE_PROJECT_DIR:-$PWD}/.claude/codegraph-turn-state.json that the
# nudge hook (codegraph-nudge.sh) consults to suppress its warning during
# the rest of the current turn.
#
# Sentinel schema: { "transcript_id": <string>, "turn_counter": <int> }
#   - transcript_id: basename of transcript_path with extension stripped
#   - turn_counter:  count of `"type":"user"` lines in the transcript file
#
# Both fields are computed the same way the nudge hook recomputes them at
# PreToolUse time, so a same-turn match suppresses the warning and a
# next-turn mismatch (new user message → counter bumps) resets it.
#
# Input:  JSON on stdin (Claude Code PostToolUse contract)
# Output: writes sentinel file; no stdout. Exit 0.
# Posture: fail-open. Any internal error → exit 0; sentinel may not be
# written, the nudge hook will simply emit its (advisory) warning.

set -uo pipefail

INPUT=$(cat 2>/dev/null || true)
[ -z "$INPUT" ] && exit 0

TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)

# Only act for codegraph MCP tools.
case "$TOOL_NAME" in
  mcp__codegraph__*) ;;
  *) exit 0 ;;
esac

TRANSCRIPT_PATH=$(echo "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null || true)
[ -z "$TRANSCRIPT_PATH" ] && exit 0
[ -f "$TRANSCRIPT_PATH" ] || exit 0

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$PWD}"
mkdir -p "$PROJECT_DIR/.claude" 2>/dev/null || exit 0

TRANSCRIPT_ID=$(basename "$TRANSCRIPT_PATH")
TRANSCRIPT_ID="${TRANSCRIPT_ID%.*}"

TURN_COUNTER=$(grep -c '"type":"user"' "$TRANSCRIPT_PATH" 2>/dev/null || echo 0)

# Atomic write via temp file to avoid the nudge hook reading a partial JSON.
SENTINEL="$PROJECT_DIR/.claude/codegraph-turn-state.json"
TMP=$(mktemp "$PROJECT_DIR/.claude/.codegraph-turn-state.XXXXXX" 2>/dev/null || true)
if [ -z "$TMP" ]; then
  exit 0
fi

if jq -n --arg tid "$TRANSCRIPT_ID" --argjson tc "$TURN_COUNTER" \
  '{transcript_id: $tid, turn_counter: $tc}' > "$TMP" 2>/dev/null; then
  mv -f "$TMP" "$SENTINEL" 2>/dev/null || rm -f "$TMP" 2>/dev/null
else
  rm -f "$TMP" 2>/dev/null
fi

exit 0
