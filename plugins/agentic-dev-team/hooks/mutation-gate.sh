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
# Test run detected — future steps will handle state tracking and mutation.
# For now, exit 0 (remaining logic added in Steps 2–8).
# ---------------------------------------------------------------------------
exit 0
