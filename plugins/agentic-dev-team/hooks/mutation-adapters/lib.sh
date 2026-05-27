#!/usr/bin/env bash
# Shared library for mutation-gate hook and adapters.
# Source this file; do not execute directly.
#
# Adapter contract (for each adapter in this directory):
# Inputs (env vars set by mutation-gate.sh orchestrator):
#   ADAPTER_TEST_FILE     — path to the test file
#   ADAPTER_SOURCE_FILE   — path to the source file under test
#   ADAPTER_TIMEOUT       — seconds (from MUTATION_GATE_TIMEOUT, default 60)
#   ADAPTER_RUNNER_STDOUT — captured test runner stdout (for pitest test-list derivation)
# Output: adapter writes normalized zero-kill list to $TMPDIR/mutation-gate/zero-kills.json
#   Format: [{"name":"TestName","file":"path.ts","line":12,"covered":4}]
#   "line": null when unknown
# Exit codes: 0 = success or advisory (orchestrator reads zero-kills.json), 1 = internal error

# ---------------------------------------------------------------------------
# _timeout — macOS-safe wrapper: timeout > gtimeout > unbounded fallback
# ---------------------------------------------------------------------------
_timeout() {
  if command -v timeout &>/dev/null; then
    timeout "$@"
  elif command -v gtimeout &>/dev/null; then
    gtimeout "$@"
  else
    # No timeout command — run unbounded; emit advisory so the user knows
    emit_advisory "MUTATION GATE ADVISORY: timeout command unavailable; mutation run has no time limit" >&2 || true
    shift
    "$@"
  fi
}

# ---------------------------------------------------------------------------
# JSON output helpers — use jq for correct escaping
# ---------------------------------------------------------------------------

# emit_block REASON — outputs {"decision":"block","reason":"..."} to stdout
emit_block() {
  jq -n --arg reason "$1" '{"decision":"block","reason":$reason}'
}

# emit_advisory MESSAGE — outputs additionalContext JSON to stdout
emit_advisory() {
  jq -n --arg ctx "$1" \
    '{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":$ctx}}'
}

# ---------------------------------------------------------------------------
# is_test_command COMMAND — returns 0 if command looks like a test runner
# ---------------------------------------------------------------------------
is_test_command() {
  local cmd="$1"
  case "$cmd" in
    npm\ test*|npm\ run\ test*) return 0 ;;
    npx\ vitest*|npx\ jest*) return 0 ;;
    mvn\ test*|mvn\ verify*|./mvnw\ test*|./mvnw\ verify*|mvnw\ test*) return 0 ;;
    gradle\ test*|./gradlew\ test*|gradlew\ test*) return 0 ;;
    dotnet\ test*) return 0 ;;
    *) return 1 ;;
  esac
}
