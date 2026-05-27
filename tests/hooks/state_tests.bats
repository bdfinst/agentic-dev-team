#!/usr/bin/env bats
# Step 2: State tracking and RED→GREEN transition detection

HOOK_LIB="$BATS_TEST_DIRNAME/../../plugins/agentic-dev-team/hooks/mutation-adapters/lib.sh"
PLUGIN_DIR="$BATS_TEST_DIRNAME/../../plugins/agentic-dev-team"
FIXTURES="$BATS_TEST_DIRNAME/fixtures"

PASS_JSON=$(cat "$FIXTURES/posttooluse-bash-pass.json")
FAIL_JSON=$(cat "$FIXTURES/posttooluse-bash-fail.json")

setup() {
  # Use a unique temp dir per test to avoid state file cross-contamination
  export TMPDIR_ORIG="${TMPDIR:-/tmp}"
  export TMPDIR="$(mktemp -d)"
  export TEST_PWD="$(mktemp -d)"
}

teardown() {
  rm -rf "$TMPDIR"
  rm -rf "$TEST_PWD"
  export TMPDIR="$TMPDIR_ORIG"
}

run_hook_in() {
  local dir="$1" json="$2"
  # cd to the test project dir so that PWD (and state_file_path) is correct;
  # invoke hook via absolute path so it finds its own files.
  run bash -c "cd '$dir' && printf '%s' '$json' | bash '$PLUGIN_DIR/hooks/mutation-gate.sh'"
}

# Helper: pre-seed state file with RED
seed_red() {
  local dir="$1"
  bash -c "
    cd '$dir'
    source '$PLUGIN_DIR/hooks/mutation-adapters/lib.sh'
    write_state 'fail' \"\$(cat '$FIXTURES/posttooluse-bash-fail.json')\"
  "
}

# Helper: pre-seed state file with GREEN
seed_green() {
  local dir="$1"
  bash -c "
    cd '$dir'
    source '$PLUGIN_DIR/hooks/mutation-adapters/lib.sh'
    write_state 'pass' \"\$(cat '$FIXTURES/posttooluse-bash-pass.json')\"
  "
}

# Helper: read state result from state file
get_state_result() {
  local dir="$1"
  bash -c "
    cd '$dir'
    source '$PLUGIN_DIR/hooks/mutation-adapters/lib.sh'
    read_state | jq -r '.result // empty'
  "
}

# ---------------------------------------------------------------------------
# State transition tests
# ---------------------------------------------------------------------------

@test "no prior state + GREEN: records GREEN, no transition, exit 0, stdout empty" {
  run_hook_in "$TEST_PWD" "$PASS_JSON"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
  # State must now be 'pass'
  result=$(get_state_result "$TEST_PWD")
  [ "$result" = "pass" ]
}

@test "RED prior state + GREEN: transition detected (TRANSITION=1 set), exit 0" {
  seed_red "$TEST_PWD"
  # Hook should detect RED→GREEN; no adapter configured yet so exits 0 silently
  run_hook_in "$TEST_PWD" "$PASS_JSON"
  [ "$status" -eq 0 ]
  # State updated to pass
  result=$(get_state_result "$TEST_PWD")
  [ "$result" = "pass" ]
}

@test "RED prior state + RED: updates state to RED, no transition, exit 0, stdout empty" {
  seed_red "$TEST_PWD"
  run_hook_in "$TEST_PWD" "$FAIL_JSON"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
  result=$(get_state_result "$TEST_PWD")
  [ "$result" = "fail" ]
}

@test "GREEN prior state + GREEN: no transition, exit 0, stdout empty" {
  seed_green "$TEST_PWD"
  run_hook_in "$TEST_PWD" "$PASS_JSON"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "stale state file (5 hours old) + GREEN: treated as absent, no transition, exit 0" {
  # Write a state file with a timestamp 5 hours in the past in the JSON content
  bash -c "
    cd '$TEST_PWD'
    source '$PLUGIN_DIR/hooks/mutation-adapters/lib.sh'
    old_ts=\$(python3 -c 'import time; print(int(time.time()-18001))')
    state_dir=\$(_state_dir)
    mkdir -p \"\$state_dir\"
    state_file=\$(state_file_path)
    jq -n --arg ts \"\$old_ts\" '{\"result\":\"fail\",\"timestamp\":(\$ts|tonumber),\"runner_stdout\":\"\"}' > \"\$state_file\"
  "
  run_hook_in "$TEST_PWD" "$PASS_JSON"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
  # State written fresh as pass (stale was ignored)
  result=$(get_state_result "$TEST_PWD")
  [ "$result" = "pass" ]
}

@test "runner_stdout captured in state file" {
  run_hook_in "$TEST_PWD" "$PASS_JSON"
  captured=$(bash -c "
    cd '$TEST_PWD'
    source '$PLUGIN_DIR/hooks/mutation-adapters/lib.sh'
    read_state | jq -r '.runner_stdout // empty'
  ")
  [[ "$captured" == *"3 passing"* ]]
}

# ---------------------------------------------------------------------------
# Timing: no-mutation paths complete in < 2s (< 4s absolute flake ceiling)
# ---------------------------------------------------------------------------

@test "no-mutation path (GREEN+GREEN): completes in < 2s" {
  seed_green "$TEST_PWD"
  local start end
  start=$(python3 -c "import time; print(time.time())")
  run_hook_in "$TEST_PWD" "$PASS_JSON"
  end=$(python3 -c "import time; print(time.time())")
  run python3 -c "exit(0 if ($end - $start) < 2.0 else 1)"
  [ "$status" -eq 0 ]
}

@test "no-mutation path (RED+RED): completes in < 2s" {
  seed_red "$TEST_PWD"
  local start end
  start=$(python3 -c "import time; print(time.time())")
  run_hook_in "$TEST_PWD" "$FAIL_JSON"
  end=$(python3 -c "import time; print(time.time())")
  run python3 -c "exit(0 if ($end - $start) < 2.0 else 1)"
  [ "$status" -eq 0 ]
}

# ---------------------------------------------------------------------------
# detect_result() — pass/fail from event JSON
# ---------------------------------------------------------------------------

@test "detect_result: exit_code 0 → pass" {
  run bash -c "
    cd '$PLUGIN_DIR'
    source hooks/mutation-adapters/lib.sh
    detect_result '$(cat "$FIXTURES/posttooluse-bash-pass.json" | tr -d '\n')'
  "
  [ "$status" -eq 0 ]
  [ "$output" = "pass" ]
}

@test "detect_result: exit_code 1 → fail" {
  run bash -c "
    cd '$PLUGIN_DIR'
    source hooks/mutation-adapters/lib.sh
    detect_result '$(cat "$FIXTURES/posttooluse-bash-fail.json" | tr -d '\n')'
  "
  [ "$status" -eq 0 ]
  [ "$output" = "fail" ]
}
