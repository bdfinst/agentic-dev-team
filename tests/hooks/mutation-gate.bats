#!/usr/bin/env bats
# Tests for hooks/mutation-gate.sh
# Step 1: fast-path, opt-out, timing

HOOK="$BATS_TEST_DIRNAME/../../plugins/agentic-dev-team/hooks/mutation-gate.sh"
PLUGIN_DIR="$BATS_TEST_DIRNAME/../../plugins/agentic-dev-team"
FAKE_BIN="$BATS_TEST_DIRNAME/fake-bin"
FIXTURES="$BATS_TEST_DIRNAME/fixtures"

# Helper: pipe JSON to the hook running from the plugin directory
run_hook() {
  local json="$1"
  shift
  run bash -c "cd '$PLUGIN_DIR' && echo '$json' | bash hooks/mutation-gate.sh"
}

# Helper: pipe JSON to the hook with env overrides
run_hook_env() {
  local env_prefix="$1"
  local json="$2"
  run bash -c "cd '$PLUGIN_DIR' && echo '$json' | $env_prefix bash hooks/mutation-gate.sh"
}

# ---------------------------------------------------------------------------
# Non-test command fast-path (< 100ms)
# ---------------------------------------------------------------------------

NON_TEST_JSON='{"tool_name":"Bash","tool_input":{"command":"echo hello"},"tool_response":{"output":"hello","error":"","interrupted":false,"exit_code":0}}'
GIT_JSON='{"tool_name":"Bash","tool_input":{"command":"git status"},"tool_response":{"output":"On branch main","error":"","interrupted":false,"exit_code":0}}'

# Returns current time in milliseconds; $EPOCHREALTIME is suppressed by bats
now_ms() { python3 -c "import time; print(int(time.time()*1000))"; }

@test "non-test command: stdout empty, exit 0" {
  run_hook "$NON_TEST_JSON"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "non-test command (git status): stdout empty, exit 0" {
  run_hook "$GIT_JSON"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "non-test command: completes in < 200ms (2x flake budget for 100ms target)" {
  local start end
  start=$(now_ms)
  run_hook "$NON_TEST_JSON"
  end=$(now_ms)
  [ $((end - start)) -lt 200 ]
}

# ---------------------------------------------------------------------------
# MUTATION_GATE_SKIP=1 opt-out
# ---------------------------------------------------------------------------

TEST_JSON='{"tool_name":"Bash","tool_input":{"command":"npm test"},"tool_response":{"output":"3 passed","error":"","interrupted":false,"exit_code":0}}'

@test "MUTATION_GATE_SKIP=1: stdout is empty (zero bytes), exit 0" {
  run_hook_env "MUTATION_GATE_SKIP=1" "$TEST_JSON"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

# ---------------------------------------------------------------------------
# Malformed / missing stdin
# ---------------------------------------------------------------------------

@test "malformed JSON stdin: stdout empty, exit 0" {
  run bash -c "cd '$PLUGIN_DIR' && echo 'not json at all' | bash hooks/mutation-gate.sh"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "empty stdin: stdout empty, exit 0" {
  run bash -c "cd '$PLUGIN_DIR' && echo '' | bash hooks/mutation-gate.sh"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "missing tool_input.command field: stdout empty, exit 0" {
  run bash -c "cd '$PLUGIN_DIR' && echo '{\"tool_name\":\"Bash\",\"tool_response\":{\"output\":\"\"}}' | bash hooks/mutation-gate.sh"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "malformed JSON: completes in < 200ms" {
  local start end
  start=$(now_ms)
  run bash -c "cd '$PLUGIN_DIR' && echo 'not json' | bash hooks/mutation-gate.sh"
  end=$(now_ms)
  [ $((end - start)) -lt 200 ]
}
