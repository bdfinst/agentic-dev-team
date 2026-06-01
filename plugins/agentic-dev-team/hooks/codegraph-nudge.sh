#!/usr/bin/env bash
# codegraph-nudge.sh — Claude Code PreToolUse hook
#
# Runs before Read, Grep, Glob tool calls. When the project has a CodeGraph
# index (.codegraph/ in cwd), nudges agents toward codegraph_* MCP tools for
# multi-file exploration. Single-file Read calls, Grep with a file `path`,
# and Glob with a literal `pattern` are passed silently.
#
# Input:  JSON on stdin (Claude Code PreToolUse contract: tool_name,
#         tool_input, transcript_path, cwd)
# Output: Warning message on stderr when exploration is detected.
#         Exit 0 = allow (silent or warn). Exit 2 = block (only in
#         careful mode — see Step 5).
#
# Posture: fail-open. Any internal error → exit 0. The hook is a nudge,
# never a gate.

set -uo pipefail

# Single-line, screen-reader-friendly, grep-friendly. The `[codegraph-nudge]`
# tag makes the source obvious in tool output. Keep this constant in sync
# with EXPECTED_WARN_MSG in tests/hooks/codegraph_nudge.bats.
WARN_MSG='[codegraph-nudge] CodeGraph is initialized in this project. Prefer codegraph_context or codegraph_explore for multi-file exploration; Grep/Glob/Read for confirming a specific detail.'

INPUT=$(cat 2>/dev/null || true)
[ -z "$INPUT" ] && exit 0

CWD=$(echo "$INPUT" | jq -r '.cwd // empty' 2>/dev/null || true)
[ -z "$CWD" ] && CWD="$PWD"

# Only act when this project has a CodeGraph index.
[ -d "$CWD/.codegraph" ] || exit 0

TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)

# Read always targets exactly one file_path — never exploration.
[ "$TOOL_NAME" = "Read" ] && exit 0

# Classify breadth from argument shape — coarse heuristic, never a true
# file-count enumeration. False positives are acceptable (the warning is
# advisory). False negatives are also acceptable.
IS_MULTI=false
case "$TOOL_NAME" in
  Grep)
    GREP_PATH=$(echo "$INPUT" | jq -r '.tool_input.path // empty' 2>/dev/null || true)
    # Multi unless path is set AND points at a regular file.
    if [ -n "$GREP_PATH" ] && [ -f "$GREP_PATH" ]; then
      IS_MULTI=false
    else
      IS_MULTI=true
    fi
    ;;
  Glob)
    GLOB_PATTERN=$(echo "$INPUT" | jq -r '.tool_input.pattern // empty' 2>/dev/null || true)
    # Multi when pattern contains a glob metacharacter.
    case "$GLOB_PATTERN" in
      *'*'*|*'?'*|*'['*) IS_MULTI=true ;;
      *) IS_MULTI=false ;;
    esac
    ;;
  *)
    # Other tools — pass silently (the hook is registered for Read|Grep|Glob
    # only; defensive default).
    exit 0
    ;;
esac

if [ "$IS_MULTI" = true ]; then
  printf '%s\n' "$WARN_MSG" >&2
fi

exit 0
