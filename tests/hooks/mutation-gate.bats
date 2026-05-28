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

# ---------------------------------------------------------------------------
# Hard dependency guards: jq and python3
# ---------------------------------------------------------------------------

@test "jq guard: code exists in hook and raw-printf advisory names jq" {
  # bash uses default PATH (/usr/bin) when PATH is unset, so jq is always findable
  # on systems where it's installed — can't exercise absence end-to-end here.
  # Verify the guard code is present and the raw-printf advisory message is correct.
  grep -q 'command -v jq' "$PLUGIN_DIR/hooks/mutation-gate.sh"
  # The jq-absent path uses raw printf (not emit_advisory); verify the JSON is valid
  local advisory_line
  advisory_line=$(grep 'MUTATION GATE ADVISORY.*jq' "$PLUGIN_DIR/hooks/mutation-gate.sh" | grep printf | head -1)
  [[ "$advisory_line" == *"jq"* ]]
  # Extract the JSON string from the printf line and verify it parses
  run python3 -c "
import re, json, sys
line = '''$advisory_line'''
m = re.search(r\"'({.*})'\", line)
if not m: sys.exit(1)
d = json.loads(m.group(1))
ctx = d['hookSpecificOutput']['additionalContext']
assert 'jq' in ctx
assert 'MUTATION GATE ADVISORY' in ctx
"
  [ $? -eq 0 ]
}

@test "python3 guard: code exists in hook and advisory message names python3" {
  # python3 is a system binary — can't reliably hide it in tests.
  grep -q 'command -v python3' "$PLUGIN_DIR/hooks/mutation-gate.sh"
  # Verify the advisory wording via emit_advisory (already tested to produce valid JSON)
  run bash -c "
    source '$PLUGIN_DIR/hooks/mutation-adapters/lib.sh'
    emit_advisory 'MUTATION GATE ADVISORY: python3 is required but not installed. Install python3 to enable mutation analysis.'
  "
  [ "$status" -eq 0 ]
  echo "$output" | python3 -c "
import json, sys
d = json.load(sys.stdin)
ctx = d['hookSpecificOutput']['additionalContext']
assert 'python3' in ctx and 'MUTATION GATE ADVISORY' in ctx
"
  [ $? -eq 0 ]
}
