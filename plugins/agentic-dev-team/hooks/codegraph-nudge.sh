#!/usr/bin/env bash
# codegraph-nudge.sh — Claude Code PreToolUse hook
#
# Runs before Read, Grep, Glob tool calls. When the project has a CodeGraph
# index (.codegraph/ in cwd), nudges agents toward codegraph_* MCP tools for
# multi-file exploration. Single-file Read calls and calls following a
# codegraph_* invocation in the same turn are passed silently.
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

INPUT=$(cat 2>/dev/null || true)
[ -z "$INPUT" ] && exit 0

CWD=$(echo "$INPUT" | jq -r '.cwd // empty' 2>/dev/null || true)
[ -z "$CWD" ] && CWD="$PWD"

# Only act when this project has a CodeGraph index.
[ -d "$CWD/.codegraph" ] || exit 0

exit 0
