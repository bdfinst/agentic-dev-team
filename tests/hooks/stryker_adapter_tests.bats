#!/usr/bin/env bats
# Step 4: Stryker (JS/TS) adapter — detect, run, parse

PLUGIN_DIR="$BATS_TEST_DIRNAME/../../plugins/dev-team"
FIXTURES="$BATS_TEST_DIRNAME/fixtures/stryker"
FAKE_BIN="$BATS_TEST_DIRNAME/fake-bin"

setup() {
  export TMPDIR="$(mktemp -d)"
  TEST_PWD="$(mktemp -d)"
  # Clear zero-kills output from prior tests
  rm -f "$TMPDIR/mutation-gate/zero-kills.json"
  mkdir -p "$TMPDIR/mutation-gate"
}

teardown() {
  rm -rf "$TMPDIR"
  rm -rf "$TEST_PWD"
}

# ---------------------------------------------------------------------------
# parse_stryker_kills REPORT_FILE — parses zero-kill tests from Stryker JSON
# ---------------------------------------------------------------------------

@test "parse_stryker_kills: zero-kill fixture returns test-C as zero-kill" {
  run bash -c "
    source '$PLUGIN_DIR/hooks/mutation-adapters/lib.sh'
    parse_stryker_kills '$FIXTURES/mutation-zero-kill.json' '$TMPDIR/mutation-gate/zero-kills.json'
    jq -r '.[].name' '$TMPDIR/mutation-gate/zero-kills.json'
  "
  [ "$status" -eq 0 ]
  [ "$output" = "test-C" ]
}

@test "parse_stryker_kills: all-killed fixture returns empty list" {
  run bash -c "
    source '$PLUGIN_DIR/hooks/mutation-adapters/lib.sh'
    parse_stryker_kills '$FIXTURES/mutation-all-killed.json' '$TMPDIR/mutation-gate/zero-kills.json'
    jq 'length' '$TMPDIR/mutation-gate/zero-kills.json'
  "
  [ "$status" -eq 0 ]
  [ "$output" = "0" ]
}

@test "parse_stryker_kills: test-D in killedBy for at least one mutant is NOT reported" {
  run bash -c "
    source '$PLUGIN_DIR/hooks/mutation-adapters/lib.sh'
    parse_stryker_kills '$FIXTURES/mutation-partial-kill.json' '$TMPDIR/mutation-gate/zero-kills.json'
    jq -r '.[].name' '$TMPDIR/mutation-gate/zero-kills.json'
  "
  [ "$status" -eq 0 ]
  [ -z "$output" ]  # test-D appears in killedBy so not reported
}

@test "parse_stryker_kills: missing line number produces line:null in output" {
  run bash -c "
    source '$PLUGIN_DIR/hooks/mutation-adapters/lib.sh'
    parse_stryker_kills '$FIXTURES/mutation-no-line.json' '$TMPDIR/mutation-gate/zero-kills.json'
    jq -r '.[0].line' '$TMPDIR/mutation-gate/zero-kills.json'
  "
  [ "$status" -eq 0 ]
  [ "$output" = "null" ]
}

@test "parse_stryker_kills: missing report file emits MUTATION GATE ADVISORY" {
  run bash -c "
    source '$PLUGIN_DIR/hooks/mutation-adapters/lib.sh'
    parse_stryker_kills '/nonexistent/path/mutation.json' '$TMPDIR/mutation-gate/zero-kills.json'
  "
  [ "$status" -eq 0 ]
  # Output should contain advisory JSON
  echo "$output" | python3 -c "
import json,sys
d=json.load(sys.stdin)
ctx=d['hookSpecificOutput']['additionalContext']
assert 'MUTATION GATE ADVISORY' in ctx
"
  [ $? -eq 0 ]
}

# ---------------------------------------------------------------------------
# stryker_detect() — checks for Stryker installation
# ---------------------------------------------------------------------------

@test "stryker_detect: package.json with @stryker-mutator/core → detected" {
  echo '{"dependencies":{"@stryker-mutator/core":"^7.0.0"}}' > "$TEST_PWD/package.json"
  run bash -c "
    cd '$TEST_PWD'
    source '$PLUGIN_DIR/hooks/mutation-adapters/stryker.sh'
    stryker_detect
  "
  [ "$status" -eq 0 ]
}

@test "stryker_detect: no package.json and no node_modules/.bin/stryker → advisory" {
  # Empty project dir
  run bash -c "
    cd '$TEST_PWD'
    source '$PLUGIN_DIR/hooks/mutation-adapters/stryker.sh'
    stryker_detect
  "
  # Should emit advisory and return non-zero (adapter not available)
  # OR emit advisory JSON to stdout and return 0 (graceful degradation)
  echo "$output" | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert 'MUTATION GATE ADVISORY' in d['hookSpecificOutput']['additionalContext']
" 2>/dev/null && [ "$status" -eq 0 ] || [ "$status" -ne 0 ]
  # Either way, output contains advisory signal
  [[ "$output" == *"MUTATION GATE ADVISORY"* ]] || [ "$status" -ne 0 ]
}

# ---------------------------------------------------------------------------
# stryker_run() — invokes fake npx stryker and produces report
# ---------------------------------------------------------------------------

@test "stryker_run: fake npx with fixture produces zero-kills.json" {
  mkdir -p "$TEST_PWD/reports/mutation"
  # Use escaped double-quotes so inner shell expands $PATH correctly
  run bash -c "
    cd '$TEST_PWD'
    export PATH=\"$FAKE_BIN:\$PATH\"
    export STRYKER_FIXTURE='$FIXTURES/mutation-zero-kill.json'
    export ADAPTER_TIMEOUT=10
    export ADAPTER_SOURCE_FILE='src/calculator.ts'
    source '$PLUGIN_DIR/hooks/mutation-adapters/stryker.sh'
    stryker_run '$TMPDIR/mutation-gate/zero-kills.json'
  "
  [ "$status" -eq 0 ]
  [ -f "$TMPDIR/mutation-gate/zero-kills.json" ]
  result=$(jq -r '.[0].name' "$TMPDIR/mutation-gate/zero-kills.json")
  [ "$result" = "test-C" ]
}

@test "stryker_run: timeout (exit 124) emits MUTATION GATE SKIPPED" {
  run bash -c "
    cd '$TEST_PWD'
    export PATH=\"$FAKE_BIN:\$PATH\"
    export STRYKER_TIMEOUT=1
    export ADAPTER_TIMEOUT=1
    export ADAPTER_SOURCE_FILE='src/calculator.ts'
    source '$PLUGIN_DIR/hooks/mutation-adapters/stryker.sh'
    stryker_run '$TMPDIR/mutation-gate/zero-kills.json'
  "
  [ "$status" -eq 0 ]
  echo "$output" | python3 -c "
import json,sys
d=json.load(sys.stdin)
ctx=d['hookSpecificOutput']['additionalContext']
assert 'MUTATION GATE SKIPPED' in ctx
"
  [ $? -eq 0 ]
}
