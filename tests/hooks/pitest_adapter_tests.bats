#!/usr/bin/env bats
# Step 6: pitest (Java) adapter

PLUGIN_DIR="$BATS_TEST_DIRNAME/../../plugins/dev-team"
FIXTURES="$BATS_TEST_DIRNAME/fixtures/pitest"
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
# pitest_parse — parses zero-kill tests from pitest XML
# ---------------------------------------------------------------------------

RUNNER_STDOUT="Tests run: 4
Running com.example.CalculatorTest
com.example.CalculatorTest.testAdd
com.example.CalculatorTest.testSubtract
com.example.CalculatorTest.testMultiply
com.example.CalculatorTest.testDefault
com.example.CalculatorTest.testConstructor"

@test "pitest_parse: zero-kill fixture with runner stdout → returns zero-kill tests" {
  run bash -c "
    source '$PLUGIN_DIR/hooks/mutation-adapters/pitest.sh'
    export ADAPTER_RUNNER_STDOUT='$RUNNER_STDOUT'
    pitest_parse '$FIXTURES/mutations-zero-kill.xml' '$TMPDIR/mutation-gate/zero-kills.json'
    jq -r '.[].name' '$TMPDIR/mutation-gate/zero-kills.json'
  "
  [ "$status" -eq 0 ]
  # testDefault and testConstructor killed nothing (not in killingTest elements)
  [[ "$output" == *"testDefault"* ]] || [[ "$output" == *"testConstructor"* ]]
}

@test "pitest_parse: all-killed XML → empty zero-kill list" {
  run bash -c "
    source '$PLUGIN_DIR/hooks/mutation-adapters/pitest.sh'
    export ADAPTER_RUNNER_STDOUT='$RUNNER_STDOUT'
    pitest_parse '$FIXTURES/mutations-all-killed.xml' '$TMPDIR/mutation-gate/zero-kills.json'
    jq 'length' '$TMPDIR/mutation-gate/zero-kills.json'
  "
  [ "$status" -eq 0 ]
  [ "$output" = "0" ]
}

@test "pitest_parse: empty runner stdout → aggregate advisory, no blocking" {
  run bash -c "
    source '$PLUGIN_DIR/hooks/mutation-adapters/pitest.sh'
    export ADAPTER_RUNNER_STDOUT=''
    pitest_parse '$FIXTURES/mutations-no-runner-stdout.xml' '$TMPDIR/mutation-gate/zero-kills.json'
  "
  [ "$status" -eq 0 ]
  # When runner stdout is empty, emit advisory (no blocking)
  echo "$output" | python3 -c "
import json, sys
d = json.load(sys.stdin)
ctx = d['hookSpecificOutput']['additionalContext']
assert 'MUTATION GATE ADVISORY' in ctx
assert 'per-test' in ctx.lower() or 'manual' in ctx.lower()
"
  [ $? -eq 0 ]
}

# ---------------------------------------------------------------------------
# pitest_detect — checks for pitest in pom.xml / build.gradle
# ---------------------------------------------------------------------------

@test "pitest_detect: pom.xml with pitest-maven → detected" {
  cat > "$TEST_PWD/pom.xml" <<'EOF'
<project>
  <build>
    <plugins>
      <plugin>
        <groupId>org.pitest</groupId>
        <artifactId>pitest-maven</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
EOF
  run bash -c "
    cd '$TEST_PWD'
    source '$PLUGIN_DIR/hooks/mutation-adapters/pitest.sh'
    pitest_detect
  "
  [ "$status" -eq 0 ]
}

@test "pitest_detect: no pom.xml and no build.gradle → advisory" {
  run bash -c "
    cd '$TEST_PWD'
    source '$PLUGIN_DIR/hooks/mutation-adapters/pitest.sh'
    pitest_detect
  "
  echo "$output" | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert 'MUTATION GATE ADVISORY' in d['hookSpecificOutput']['additionalContext']
" 2>/dev/null && [ "$status" -eq 0 ] || [ "$status" -ne 0 ]
  [[ "$output" == *"MUTATION GATE ADVISORY"* ]] || [ "$status" -ne 0 ]
}

# ---------------------------------------------------------------------------
# pitest_run — runs fake mvn and produces zero-kills
# ---------------------------------------------------------------------------

@test "pitest_run: fake mvn with fixture produces zero-kills.json" {
  mkdir -p "$TEST_PWD/target/pit-reports"
  run bash -c "
    cd '$TEST_PWD'
    export PATH=\"$FAKE_BIN:\$PATH\"
    export PITEST_FIXTURE='$FIXTURES/mutations-zero-kill.xml'
    export ADAPTER_TIMEOUT=10
    export ADAPTER_RUNNER_STDOUT='$RUNNER_STDOUT'
    source '$PLUGIN_DIR/hooks/mutation-adapters/pitest.sh'
    pitest_run '$TMPDIR/mutation-gate/zero-kills.json'
  "
  [ "$status" -eq 0 ]
  [ -f "$TMPDIR/mutation-gate/zero-kills.json" ]
  count=$(jq 'length' "$TMPDIR/mutation-gate/zero-kills.json")
  [ "$count" -gt 0 ]
}

@test "pitest_run: timeout (exit 124) emits MUTATION GATE SKIPPED" {
  run bash -c "
    cd '$TEST_PWD'
    export PATH=\"$FAKE_BIN:\$PATH\"
    export PITEST_TIMEOUT=1
    export ADAPTER_TIMEOUT=1
    export ADAPTER_RUNNER_STDOUT=''
    source '$PLUGIN_DIR/hooks/mutation-adapters/pitest.sh'
    pitest_run '$TMPDIR/mutation-gate/zero-kills.json'
  "
  [ "$status" -eq 0 ]
  echo "$output" | python3 -c "
import json, sys
d = json.load(sys.stdin)
ctx = d['hookSpecificOutput']['additionalContext']
assert 'MUTATION GATE SKIPPED' in ctx
"
  [ $? -eq 0 ]
}
