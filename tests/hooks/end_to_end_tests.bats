#!/usr/bin/env bats
# Step 5: End-to-end JS/TS flow — blocking output, exit codes, prefix tokens

PLUGIN_DIR="$BATS_TEST_DIRNAME/../../plugins/dev-team"
FIXTURES="$BATS_TEST_DIRNAME/fixtures"
FAKE_BIN="$BATS_TEST_DIRNAME/fake-bin"

setup() {
  export TMPDIR="$(mktemp -d)"
  TEST_PWD="$(mktemp -d)"
  # Seed a package.json so stryker_detect passes
  echo '{"dependencies":{"@stryker-mutator/core":"^7.0.0"}}' > "$TEST_PWD/package.json"
  mkdir -p "$TEST_PWD/reports/mutation"
}

teardown() {
  rm -rf "$TMPDIR" "$TEST_PWD"
}

# Seed RED state then run hook with a passing test command
run_e2e() {
  local fixture="$1"  # stryker fixture to use
  local timeout="${2:-1}"   # adapter timeout (short for tests)
  # Seed RED
  bash -c "
    cd '$TEST_PWD'
    source '$PLUGIN_DIR/hooks/mutation-adapters/lib.sh'
    write_state 'fail' \"\$(cat '$FIXTURES/posttooluse-bash-fail.json')\"
  "
  # Run hook with GREEN event
  run bash -c "
    cd '$TEST_PWD'
    export PATH=\"$FAKE_BIN:\$PATH\"
    export STRYKER_FIXTURE='$fixture'
    export MUTATION_GATE_TIMEOUT=$timeout
    printf '%s' \"\$(cat '$FIXTURES/posttooluse-bash-pass.json')\" | \
      bash '$PLUGIN_DIR/hooks/mutation-gate.sh'
  "
}

# ---------------------------------------------------------------------------
# Blocking: zero-kill tests → decision:block JSON, exit 0
# ---------------------------------------------------------------------------

@test "end-to-end: zero-kill tests → MUTATION GATE BLOCKED JSON, exit 0" {
  run_e2e "$FIXTURES/stryker/mutation-zero-kill.json"
  [ "$status" -eq 0 ]
  # stdout must be valid JSON with decision:block
  echo "$output" | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d['decision'] == 'block', f'expected decision:block, got {d}'
assert 'MUTATION GATE BLOCKED' in d['reason'], f'expected MUTATION GATE BLOCKED in reason'
assert 'test-C' in d['reason'], f'expected test-C in reason'
assert 'Covered' in d['reason'], f'expected Covered count in reason'
assert 'Fix these tests before continuing' in d['reason']
"
  [ $? -eq 0 ]
}

@test "end-to-end: blocking message contains guidance on what a mutation-killing test looks like" {
  run_e2e "$FIXTURES/stryker/mutation-zero-kill.json"
  [ "$status" -eq 0 ]
  echo "$output" | python3 -c "
import json, sys
d = json.load(sys.stdin)
reason = d['reason']
# Must contain actionable guidance
assert 'assert' in reason.lower() or 'assertion' in reason.lower(), 'expected guidance about assertions'
"
  [ $? -eq 0 ]
}

# ---------------------------------------------------------------------------
# Pass: all tests kill mutants → stdout empty, exit 0
# ---------------------------------------------------------------------------

@test "end-to-end: all tests kill mutants → stdout empty, exit 0" {
  run_e2e "$FIXTURES/stryker/mutation-all-killed.json"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

# ---------------------------------------------------------------------------
# Timeout → MUTATION GATE SKIPPED advisory JSON, exit 0
# ---------------------------------------------------------------------------

@test "end-to-end: timeout → MUTATION GATE SKIPPED advisory JSON, exit 0" {
  # Seed RED
  bash -c "
    cd '$TEST_PWD'
    source '$PLUGIN_DIR/hooks/mutation-adapters/lib.sh'
    write_state 'fail' \"\$(cat '$FIXTURES/posttooluse-bash-fail.json')\"
  "
  run bash -c "
    cd '$TEST_PWD'
    export PATH=\"$FAKE_BIN:\$PATH\"
    export STRYKER_TIMEOUT=1
    export MUTATION_GATE_TIMEOUT=1
    printf '%s' \"\$(cat '$FIXTURES/posttooluse-bash-pass.json')\" | \
      bash '$PLUGIN_DIR/hooks/mutation-gate.sh'
  "
  [ "$status" -eq 0 ]
  echo "$output" | python3 -c "
import json, sys
d = json.load(sys.stdin)
ctx = d['hookSpecificOutput']['additionalContext']
assert 'MUTATION GATE SKIPPED' in ctx, f'got: {ctx}'
assert 'timeout' in ctx.lower(), f'expected timeout message, got: {ctx}'
"
  [ $? -eq 0 ]
}

# ---------------------------------------------------------------------------
# Tool not installed → MUTATION GATE ADVISORY, exit 0
# ---------------------------------------------------------------------------

@test "end-to-end: Stryker not installed → MUTATION GATE ADVISORY, exit 0" {
  # Project with no package.json and no node_modules
  local bare_dir
  bare_dir="$(mktemp -d)"
  # Seed RED in bare_dir
  bash -c "
    cd '$bare_dir'
    source '$PLUGIN_DIR/hooks/mutation-adapters/lib.sh'
    write_state 'fail' \"\$(cat '$FIXTURES/posttooluse-bash-fail.json')\"
  "
  run bash -c "
    cd '$bare_dir'
    export PATH=\"$FAKE_BIN:\$PATH\"
    printf '%s' \"\$(cat '$FIXTURES/posttooluse-bash-pass.json')\" | \
      bash '$PLUGIN_DIR/hooks/mutation-gate.sh'
  "
  rm -rf "$bare_dir"
  [ "$status" -eq 0 ]
  echo "$output" | python3 -c "
import json, sys
d = json.load(sys.stdin)
ctx = d['hookSpecificOutput']['additionalContext']
assert 'MUTATION GATE ADVISORY' in ctx
"
  [ $? -eq 0 ]
}

# ---------------------------------------------------------------------------
# MUTATION_GATE_SKIP=1 → stdout empty, exit 0
# ---------------------------------------------------------------------------

@test "end-to-end: MUTATION_GATE_SKIP=1 → stdout empty (zero bytes), exit 0" {
  run bash -c "
    cd '$TEST_PWD'
    export MUTATION_GATE_SKIP=1
    printf '%s' \"\$(cat '$FIXTURES/posttooluse-bash-pass.json')\" | \
      bash '$PLUGIN_DIR/hooks/mutation-gate.sh'
  "
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

# ---------------------------------------------------------------------------
# No prior state → stdout empty, exit 0
# ---------------------------------------------------------------------------

@test "end-to-end: no prior state + GREEN → stdout empty, exit 0" {
  run bash -c "
    cd '$TEST_PWD'
    export PATH=\"$FAKE_BIN:\$PATH\"
    printf '%s' \"\$(cat '$FIXTURES/posttooluse-bash-pass.json')\" | \
      bash '$PLUGIN_DIR/hooks/mutation-gate.sh'
  "
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

# ---------------------------------------------------------------------------
# Prefix token consistency — every non-silent output starts with a known token
# ---------------------------------------------------------------------------

@test "prefix token: blocking output starts with MUTATION GATE BLOCKED" {
  run_e2e "$FIXTURES/stryker/mutation-zero-kill.json"
  [ "$status" -eq 0 ]
  # Extract the reason and check first word
  first=$(echo "$output" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('reason','')[:20])")
  [[ "$first" == *"MUTATION GATE BLOCKED"* ]] || [[ "$first" == "MUTATION GATE BLOCKED"* ]]
  echo "$output" | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d['reason'].startswith('MUTATION GATE BLOCKED'), f'reason must start with MUTATION GATE BLOCKED, got: {d[\"reason\"][:50]}'
"
  [ $? -eq 0 ]
}
