#!/usr/bin/env bash
# JS FP Review Hook — PostToolUse advisory for Write/Edit on JS/TS files
# Detects common mutation patterns and warns without blocking.
# Full nuanced analysis is handled by the js-fp-review agent.

set -euo pipefail

# Read tool input from stdin
INPUT=$(cat)

# Extract the file path from the tool input (using jq for robust JSON parsing)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.path // .file_path // .path // empty' 2>/dev/null || true)

# Only check JS/TS files
case "$FILE_PATH" in
  *.js|*.ts|*.jsx|*.tsx) ;;
  *) exit 0 ;;
esac

# Skip if file doesn't exist
[ -f "$FILE_PATH" ] || exit 0

WARNINGS=""

# Array mutation methods
ARRAY_MUTATIONS=$(grep -n '\.\(push\|pop\|shift\|unshift\|splice\|reverse\|sort\|fill\|copyWithin\)\s*(' "$FILE_PATH" 2>/dev/null | grep -v '\[\.\.\..*\]\.' | grep -v '^\s*//' || true)
if [ -n "$ARRAY_MUTATIONS" ]; then
  WARNINGS="${WARNINGS}
FP: Array mutation detected — consider immutable alternatives (spread, slice, toSorted, toReversed):
${ARRAY_MUTATIONS}"
fi

# Global state mutations
GLOBAL_MUTATIONS=$(grep -n '\b\(window\|global\|globalThis\)\.\w\+\s*=[^=]' "$FILE_PATH" 2>/dev/null | grep -v '^\s*//' || true)
PROCESS_ENV=$(grep -n 'process\.env\.\w\+\s*=[^=]' "$FILE_PATH" 2>/dev/null | grep -v '^\s*//' || true)
if [ -n "$GLOBAL_MUTATIONS" ] || [ -n "$PROCESS_ENV" ]; then
  WARNINGS="${WARNINGS}
FP: Global state mutation detected — use module-level state or dependency injection:
${GLOBAL_MUTATIONS}${PROCESS_ENV}"
fi

# Object.assign with existing target
OBJECT_ASSIGN=$(grep -n 'Object\.assign\s*(\s*[a-zA-Z_]\w*\s*,' "$FILE_PATH" 2>/dev/null | grep -v 'Object\.assign\s*(\s*{}' | grep -v '^\s*//' || true)
if [ -n "$OBJECT_ASSIGN" ]; then
  WARNINGS="${WARNINGS}
FP: Object.assign mutates target in place — use spread or Object.assign({}, ...):
${OBJECT_ASSIGN}"
fi

# Parameter property assignment (basic heuristic)
PARAM_MUTATION=$(grep -n '\b\(param\|params\|options\|opts\|config\|cfg\|obj\|data\|input\|args\|req\|res\)\.\w\+\s*=[^=]' "$FILE_PATH" 2>/dev/null | grep -v '^\s*//' | grep -v '\bthis\.' || true)
if [ -n "$PARAM_MUTATION" ]; then
  WARNINGS="${WARNINGS}
FP: Possible parameter mutation — create a new object with spread instead:
${PARAM_MUTATION}"
fi

if [ -n "$WARNINGS" ]; then
  echo "$WARNINGS"
fi

exit 0
