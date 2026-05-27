#!/usr/bin/env bats
# Step 3: Language adapter detection and dispatch

PLUGIN_DIR="$BATS_TEST_DIRNAME/../../plugins/agentic-dev-team"
FIXTURES="$BATS_TEST_DIRNAME/fixtures"

# Helper: simulate a RED→GREEN transition then call the hook
# The hook must have a RED state pre-seeded to detect transition
run_after_red() {
  local dir="$1" json="$2"
  # Seed RED state
  bash -c "
    cd '$dir'
    source '$PLUGIN_DIR/hooks/mutation-adapters/lib.sh'
    write_state 'fail' \"\$(cat '$FIXTURES/posttooluse-bash-fail.json')\"
  "
  # Run hook
  run bash -c "cd '$dir' && printf '%s' '$json' | bash '$PLUGIN_DIR/hooks/mutation-gate.sh'"
}

make_pass_json() {
  local cmd="$1" output="${2:-tests passed}"
  jq -n --arg cmd "$cmd" --arg out "$output" \
    '{"tool_name":"Bash","tool_input":{"command":$cmd},"tool_response":{"output":$out,"error":"","interrupted":false,"exit_code":0}}'
}

setup() {
  export TMPDIR="$(mktemp -d)"
  TEST_PWD="$(mktemp -d)"
}

teardown() {
  rm -rf "$TMPDIR"
  rm -rf "$TEST_PWD"
}

# ---------------------------------------------------------------------------
# detect_adapter() dispatches to the correct adapter by command
# ---------------------------------------------------------------------------

@test "detect_adapter: npm test → stryker" {
  run bash -c "
    source '$PLUGIN_DIR/hooks/mutation-adapters/lib.sh'
    detect_adapter 'npm test'
  "
  [ "$status" -eq 0 ]
  [ "$output" = "stryker" ]
}

@test "detect_adapter: npx vitest run → stryker" {
  run bash -c "
    source '$PLUGIN_DIR/hooks/mutation-adapters/lib.sh'
    detect_adapter 'npx vitest run'
  "
  [ "$status" -eq 0 ]
  [ "$output" = "stryker" ]
}

@test "detect_adapter: npx jest → stryker" {
  run bash -c "
    source '$PLUGIN_DIR/hooks/mutation-adapters/lib.sh'
    detect_adapter 'npx jest'
  "
  [ "$status" -eq 0 ]
  [ "$output" = "stryker" ]
}

@test "detect_adapter: mvn test → pitest" {
  run bash -c "
    source '$PLUGIN_DIR/hooks/mutation-adapters/lib.sh'
    detect_adapter 'mvn test'
  "
  [ "$status" -eq 0 ]
  [ "$output" = "pitest" ]
}

@test "detect_adapter: ./gradlew test → pitest" {
  run bash -c "
    source '$PLUGIN_DIR/hooks/mutation-adapters/lib.sh'
    detect_adapter './gradlew test'
  "
  [ "$status" -eq 0 ]
  [ "$output" = "pitest" ]
}

@test "detect_adapter: mvnw test → pitest" {
  run bash -c "
    source '$PLUGIN_DIR/hooks/mutation-adapters/lib.sh'
    detect_adapter './mvnw test'
  "
  [ "$status" -eq 0 ]
  [ "$output" = "pitest" ]
}

@test "detect_adapter: dotnet test → stryker-net" {
  run bash -c "
    source '$PLUGIN_DIR/hooks/mutation-adapters/lib.sh'
    detect_adapter 'dotnet test'
  "
  [ "$status" -eq 0 ]
  [ "$output" = "stryker-net" ]
}

@test "detect_adapter: python -m pytest → none" {
  run bash -c "
    source '$PLUGIN_DIR/hooks/mutation-adapters/lib.sh'
    detect_adapter 'python -m pytest'
  "
  [ "$status" -eq 0 ]
  [ "$output" = "none" ]
}

@test "detect_adapter: unknown command → none" {
  run bash -c "
    source '$PLUGIN_DIR/hooks/mutation-adapters/lib.sh'
    detect_adapter 'cargo test'
  "
  [ "$status" -eq 0 ]
  [ "$output" = "none" ]
}

# ---------------------------------------------------------------------------
# Unsupported language advisory: hook exits 0, stdout is advisory JSON
# ---------------------------------------------------------------------------

@test "RED→GREEN with python pytest: emits MUTATION GATE ADVISORY, exit 0" {
  local json
  json=$(make_pass_json "python -m pytest" "3 passed")
  run_after_red "$TEST_PWD" "$json"
  [ "$status" -eq 0 ]
  # stdout must be advisory JSON
  echo "$output" | python3 -c "
import json,sys
d=json.load(sys.stdin)
ctx=d['hookSpecificOutput']['additionalContext']
assert 'MUTATION GATE ADVISORY' in ctx, f'expected advisory, got: {ctx}'
assert 'no adapter' in ctx.lower(), f'expected no adapter message, got: {ctx}'
" || {
    echo "output was: $output"
    false
  }
}
