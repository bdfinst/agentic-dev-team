#!/usr/bin/env bats
# Step 7: Stryker.NET (C#) adapter

PLUGIN_DIR="$BATS_TEST_DIRNAME/../../plugins/agentic-dev-team"
FIXTURES="$BATS_TEST_DIRNAME/fixtures/stryker-net"
FAKE_BIN="$BATS_TEST_DIRNAME/fake-bin"

setup() {
  export TMPDIR="$(mktemp -d)"
  TEST_PWD="$(mktemp -d)"
  mkdir -p "$TMPDIR/mutation-gate"
}

teardown() {
  rm -rf "$TMPDIR" "$TEST_PWD"
}

# ---------------------------------------------------------------------------
# parse_stryker_kills reused for Stryker.NET (same JSON schema)
# ---------------------------------------------------------------------------

@test "Stryker.NET fixture: parse_stryker_kills returns CalculatorTests.TestDefault as zero-kill" {
  run bash -c "
    source '$PLUGIN_DIR/hooks/mutation-adapters/lib.sh'
    parse_stryker_kills '$FIXTURES/mutation-report-zero-kill.json' '$TMPDIR/mutation-gate/zero-kills.json'
    jq -r '.[].name' '$TMPDIR/mutation-gate/zero-kills.json'
  "
  [ "$status" -eq 0 ]
  [ "$output" = "CalculatorTests.TestDefault" ]
}

# ---------------------------------------------------------------------------
# stryker_net_detect
# ---------------------------------------------------------------------------

@test "stryker_net_detect: dotnet-tools.json with dotnet-stryker → detected" {
  mkdir -p "$TEST_PWD/.config"
  cat > "$TEST_PWD/.config/dotnet-tools.json" <<'EOF'
{
  "version": 1,
  "isRoot": true,
  "tools": {
    "dotnet-stryker": {
      "version": "4.0.0",
      "commands": ["dotnet-stryker"]
    }
  }
}
EOF
  run bash -c "
    cd '$TEST_PWD'
    source '$PLUGIN_DIR/hooks/mutation-adapters/stryker-net.sh'
    stryker_net_detect
  "
  [ "$status" -eq 0 ]
}

@test "stryker_net_detect: fake dotnet stryker --version → detected" {
  run bash -c "
    cd '$TEST_PWD'
    export PATH=\"$FAKE_BIN:\$PATH\"
    source '$PLUGIN_DIR/hooks/mutation-adapters/stryker-net.sh'
    stryker_net_detect
  "
  [ "$status" -eq 0 ]
}

@test "stryker_net_detect: no dotnet-tools.json and no dotnet command → advisory" {
  run bash -c "
    cd '$TEST_PWD'
    export PATH='/usr/bin:/bin'
    source '$PLUGIN_DIR/hooks/mutation-adapters/stryker-net.sh'
    stryker_net_detect
  "
  [[ "$output" == *"MUTATION GATE ADVISORY"* ]] || [ "$status" -ne 0 ]
}

# ---------------------------------------------------------------------------
# stryker_net_run
# ---------------------------------------------------------------------------

@test "stryker_net_run: fake dotnet with fixture produces zero-kills.json" {
  mkdir -p "$TEST_PWD/StrykerOutput"
  run bash -c "
    cd '$TEST_PWD'
    export PATH=\"$FAKE_BIN:\$PATH\"
    export STRYKER_NET_FIXTURE='$FIXTURES/mutation-report-zero-kill.json'
    export ADAPTER_TIMEOUT=10
    export ADAPTER_SOURCE_FILE='Calculator.cs'
    source '$PLUGIN_DIR/hooks/mutation-adapters/stryker-net.sh'
    stryker_net_run '$TMPDIR/mutation-gate/zero-kills.json'
  "
  [ "$status" -eq 0 ]
  [ -f "$TMPDIR/mutation-gate/zero-kills.json" ]
  result=$(jq -r '.[0].name' "$TMPDIR/mutation-gate/zero-kills.json")
  [ "$result" = "CalculatorTests.TestDefault" ]
}

@test "stryker_net_run: timeout emits MUTATION GATE SKIPPED" {
  run bash -c "
    cd '$TEST_PWD'
    export PATH=\"$FAKE_BIN:\$PATH\"
    export STRYKER_NET_TIMEOUT=1
    export ADAPTER_TIMEOUT=1
    source '$PLUGIN_DIR/hooks/mutation-adapters/stryker-net.sh'
    stryker_net_run '$TMPDIR/mutation-gate/zero-kills.json'
  "
  [ "$status" -eq 0 ]
  echo "$output" | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert 'MUTATION GATE SKIPPED' in d['hookSpecificOutput']['additionalContext']
"
  [ $? -eq 0 ]
}

@test "stryker_run and stryker_net_run are separate functions (not unified)" {
  run bash -c "
    source '$PLUGIN_DIR/hooks/mutation-adapters/stryker.sh'
    source '$PLUGIN_DIR/hooks/mutation-adapters/stryker-net.sh'
    declare -f stryker_run | head -1
    declare -f stryker_net_run | head -1
  "
  [[ "$output" == *"stryker_run"* ]]
  [[ "$output" == *"stryker_net_run"* ]]
}
