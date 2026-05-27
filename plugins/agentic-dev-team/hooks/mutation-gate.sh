#!/usr/bin/env bash
# mutation-gate.sh — PostToolUse hook for Bash tool calls.
#
# After each RED-to-GREEN test transition, runs mutation testing scoped to
# the affected test file and blocks tests that kill zero mutants.
#
# Output protocol (PostToolUse):
#   Blocking : emit_block JSON to stdout, exit 0
#   Advisory : emit_advisory JSON to stdout, exit 0
#   Silent   : no stdout, exit 0

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=hooks/mutation-adapters/lib.sh
source "$SCRIPT_DIR/mutation-adapters/lib.sh"

# ---------------------------------------------------------------------------
# Opt-out
# ---------------------------------------------------------------------------
[ "${MUTATION_GATE_SKIP:-0}" = "1" ] && exit 0

# ---------------------------------------------------------------------------
# Parse stdin (PostToolUse event JSON)
# ---------------------------------------------------------------------------
INPUT=$(cat)

COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
[ -n "$COMMAND" ] || exit 0

# ---------------------------------------------------------------------------
# Fast-path: not a test command
# ---------------------------------------------------------------------------
is_test_command "$COMMAND" || exit 0

# ---------------------------------------------------------------------------
# Test run detected — determine pass/fail and update state
# ---------------------------------------------------------------------------
CURRENT_RESULT=$(detect_result "$INPUT")

PREV_STATE=$(read_state)
PREV_RESULT=$(echo "$PREV_STATE" | jq -r '.result // "none"' 2>/dev/null || echo "none")

write_state "$CURRENT_RESULT" "$INPUT"

# ---------------------------------------------------------------------------
# Check for RED→GREEN transition
# ---------------------------------------------------------------------------
is_red_to_green "$PREV_RESULT" "$CURRENT_RESULT" || exit 0

# ---------------------------------------------------------------------------
# RED→GREEN detected — detect adapter
# ---------------------------------------------------------------------------
ADAPTER=$(detect_adapter "$COMMAND")

if [ "$ADAPTER" = "none" ]; then
  emit_advisory "MUTATION GATE ADVISORY: no adapter for this language. Install Stryker (JS/TS), pitest (Java), or Stryker.NET (C#) to enable per-test kill analysis."
  exit 0
fi

# ---------------------------------------------------------------------------
# Adapter dispatch (adapter files added in Steps 4–7)
# ---------------------------------------------------------------------------
exit 0
