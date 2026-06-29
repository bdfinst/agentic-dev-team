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

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=hooks/mutation-adapters/lib.sh
# shellcheck disable=SC1091
source "$SCRIPT_DIR/mutation-adapters/lib.sh"

# ---------------------------------------------------------------------------
# Hard dependency guards — must come before any jq or python3 call
# ---------------------------------------------------------------------------
if ! command -v jq &>/dev/null; then
  # Cannot call emit_advisory (requires jq); use raw printf for the JSON
  printf '{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"MUTATION GATE ADVISORY: jq is required but not installed. Run /init-dev-team to install it, or: brew install jq (macOS) / apt install jq (Linux) / winget install jqlang.jq (Windows)."}}\n'
  exit 0
fi

if ! command -v python3 &>/dev/null; then
  emit_advisory "MUTATION GATE ADVISORY: python3 is required but not installed. Run /init-dev-team to install it, or: brew install python3 (macOS) / apt install python3 (Linux) / winget install Python.Python.3 (Windows)."
  exit 0
fi

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
  emit_advisory "MUTATION GATE ADVISORY: no mutation testing adapter for this language. Run /init-dev-team to install one (supports JS/TS via Stryker, Java via pitest, C# via Stryker.NET)."
  exit 0
fi

# ---------------------------------------------------------------------------
# Adapter dispatch
# ---------------------------------------------------------------------------
ZERO_KILLS_FILE="${TMPDIR:-/tmp}/mutation-gate/zero-kills.json"
mkdir -p "$(dirname "$ZERO_KILLS_FILE")"

export ADAPTER_TIMEOUT="${MUTATION_GATE_TIMEOUT:-60}"
export ADAPTER_COMMAND="$COMMAND"
export ADAPTER_RUNNER_STDOUT
ADAPTER_RUNNER_STDOUT=$(echo "$PREV_STATE" | jq -r '.runner_stdout // ""' 2>/dev/null || true)

case "$ADAPTER" in
  stryker)
    # shellcheck source=hooks/mutation-adapters/stryker.sh
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/mutation-adapters/stryker.sh"
    stryker_detect || exit 0
    ADAPTER_SOURCE_FILE=$(derive_source_file "${COMMAND##* }" 2>/dev/null || true)
    export ADAPTER_SOURCE_FILE
    stryker_run "$ZERO_KILLS_FILE"
    ;;
  pitest)
    # shellcheck source=hooks/mutation-adapters/pitest.sh
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/mutation-adapters/pitest.sh"
    pitest_detect || exit 0
    pitest_run "$ZERO_KILLS_FILE"
    ;;
  stryker-net)
    # shellcheck source=hooks/mutation-adapters/stryker-net.sh
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/mutation-adapters/stryker-net.sh"
    stryker_net_detect || exit 0
    stryker_net_run "$ZERO_KILLS_FILE"
    ;;
  mutmut)
    # shellcheck source=hooks/mutation-adapters/mutmut.sh
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/mutation-adapters/mutmut.sh"
    mutmut_detect || exit 0
    mutmut_run "$ZERO_KILLS_FILE"
    ;;
esac

# ---------------------------------------------------------------------------
# Emit block if zero-kill tests found
# ---------------------------------------------------------------------------
if [ -f "$ZERO_KILLS_FILE" ] && [ "$(jq 'length' "$ZERO_KILLS_FILE" 2>/dev/null)" != "0" ]; then
  REASON=$(format_blocking_reason "$ZERO_KILLS_FILE" "$COMMAND")
  emit_block "$REASON"
fi

exit 0
