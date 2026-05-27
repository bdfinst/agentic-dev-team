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
# State file management
#
# State file stores: result (pass/fail), timestamp (Unix seconds),
# runner_stdout (full output, truncated at 64KB).
# Location: $TMPDIR/mutation-gate/session-<12-char sha256 of PWD>
# TTL: 4 hours (14400 seconds)
# ---------------------------------------------------------------------------

_state_dir() {
  echo "${TMPDIR:-/tmp}/mutation-gate"
}

# state_file_path — prints the path to this project's state file
state_file_path() {
  local hash
  hash=$(printf '%s' "${PWD}" | sha256sum 2>/dev/null | cut -c1-12 || \
         printf '%s' "${PWD}" | shasum -a 256 2>/dev/null | cut -c1-12 || \
         printf '%s' "${PWD}" | md5sum 2>/dev/null | cut -c1-12)
  echo "$(_state_dir)/session-${hash}"
}

# write_state RESULT EVENT_JSON — writes state file from a PostToolUse event
write_state() {
  local result="$1"
  local event_json="$2"
  local state_dir
  state_dir=$(_state_dir)
  mkdir -p "$state_dir"
  # Purge stale files (> 4 hours)
  find "$state_dir" -name "session-*" -mmin +240 -delete 2>/dev/null || true
  local runner_stdout
  # Truncate runner_stdout at 64KB
  runner_stdout=$(echo "$event_json" | jq -r '.tool_response.output // ""' 2>/dev/null | head -c 65536)
  local ts
  ts=$(date +%s)
  jq -n \
    --arg result "$result" \
    --arg ts "$ts" \
    --arg stdout "$runner_stdout" \
    '{"result":$result,"timestamp":($ts|tonumber),"runner_stdout":$stdout}' \
    > "$(state_file_path)"
}

# read_state — prints state JSON or empty if absent/stale
read_state() {
  local state_file
  state_file=$(state_file_path)
  [ -f "$state_file" ] || return 0
  local ts now age
  ts=$(jq -r '.timestamp // 0' "$state_file" 2>/dev/null)
  now=$(date +%s)
  age=$(( now - ts ))
  if [ "$age" -gt 14400 ]; then
    rm -f "$state_file"
    return 0
  fi
  cat "$state_file"
}

# detect_result EVENT_JSON — prints "pass" or "fail" from PostToolUse event
detect_result() {
  local event_json="$1"
  local exit_code
  exit_code=$(echo "$event_json" | jq -r '.tool_response.exit_code // -1' 2>/dev/null)
  # Primary: exit_code
  if [ "$exit_code" = "0" ]; then
    echo "pass"
    return 0
  elif [ "$exit_code" != "-1" ] && [ "$exit_code" != "null" ]; then
    echo "fail"
    return 0
  fi
  # Secondary: stdout patterns (for runners that always exit 0)
  local output
  output=$(echo "$event_json" | jq -r '.tool_response.output // ""' 2>/dev/null)
  if echo "$output" | grep -qiE '(passing|tests run.*failures: 0|all tests passed|✓|ok [0-9])'; then
    echo "pass"
  elif echo "$output" | grep -qiE '(failing|failures: [1-9]|error:|FAILED)'; then
    echo "fail"
  else
    echo "fail"
  fi
}

# is_red_to_green PREV_RESULT CUR_RESULT — returns 0 if RED→GREEN transition
is_red_to_green() {
  [ "$1" = "fail" ] && [ "$2" = "pass" ]
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
    python\ *pytest*|pytest\ *) return 0 ;;
    go\ test*) return 0 ;;
    cargo\ test*) return 0 ;;
    *) return 1 ;;
  esac
}

# ---------------------------------------------------------------------------
# detect_adapter COMMAND — prints adapter name: stryker | pitest | stryker-net | none
# ---------------------------------------------------------------------------
detect_adapter() {
  local cmd="$1"
  case "$cmd" in
    npm\ test*|npm\ run\ test*|npx\ vitest*|npx\ jest*) echo "stryker" ;;
    mvn\ test*|mvn\ verify*|./mvnw\ test*|./mvnw\ verify*|mvnw\ test*|\
    gradle\ test*|./gradlew\ test*|gradlew\ test*) echo "pitest" ;;
    dotnet\ test*) echo "stryker-net" ;;
    *) echo "none" ;;
  esac
}
