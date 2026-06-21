#!/usr/bin/env bats
# Tests for hooks/mutation-adapters/lib.sh

HOOK_LIB="$BATS_TEST_DIRNAME/../../plugins/dev-team/hooks/mutation-adapters/lib.sh"
FAKE_BIN="$BATS_TEST_DIRNAME/fake-bin"

setup() {
  mkdir -p "$FAKE_BIN"
}

teardown() {
  rm -f "$FAKE_BIN/timeout" "$FAKE_BIN/gtimeout"
}

# ---------------------------------------------------------------------------
# _timeout() — wrapper for timeout/gtimeout/neither
# ---------------------------------------------------------------------------

@test "_timeout: uses 'timeout' when available" {
  # Create a fake 'timeout' that records it was called
  cat > "$FAKE_BIN/timeout" <<'EOF'
#!/usr/bin/env bash
echo "CALLED:timeout $*"
exit 0
EOF
  chmod +x "$FAKE_BIN/timeout"

  # Remove gtimeout from fake-bin so only 'timeout' is present
  rm -f "$FAKE_BIN/gtimeout"

  run bash -c "
    export PATH=\"$FAKE_BIN:\$PATH\"
    source '$HOOK_LIB'
    _timeout 5 echo hello
  "
  [ "$status" -eq 0 ]
  [[ "$output" == *"CALLED:timeout"* ]]
}

@test "_timeout: uses 'gtimeout' when 'timeout' unavailable" {
  # Create fake gtimeout using /bin/sh (direct path, no env lookup needed)
  cat > "$FAKE_BIN/gtimeout" <<'EOF'
#!/bin/sh
echo "CALLED:gtimeout $*"
exit 0
EOF
  chmod +x "$FAKE_BIN/gtimeout"
  rm -f "$FAKE_BIN/timeout"

  # PATH is JUST the fake-bin so the host's real 'timeout' (present at
  # /usr/bin/timeout on Linux, absent on a basic macOS path) can never be found
  # — that is the condition under test. The wrapped `echo` is a shell builtin
  # and the fake gtimeout has an absolute `/bin/sh` shebang, so neither needs a
  # system PATH.
  run bash -c "
    export PATH=\"$FAKE_BIN\"
    source '$HOOK_LIB'
    _timeout 5 echo hello
  "
  [ "$status" -eq 0 ]
  [[ "$output" == *"CALLED:gtimeout"* ]]
}

@test "_timeout: runs command unbounded when neither timeout nor gtimeout available" {
  # Empty fake-bin — no timeout, no gtimeout
  rm -f "$FAKE_BIN/timeout" "$FAKE_BIN/gtimeout"

  # PATH is JUST the fake-bin (now empty) so neither timeout nor gtimeout
  # resolves on any host; `echo` is a builtin so the unbounded fallback still
  # runs the command.
  run bash -c "
    export PATH=\"$FAKE_BIN\"
    source '$HOOK_LIB'
    _timeout 5 echo hello_unbounded
  " 2>&1
  [ "$status" -eq 0 ]
  [[ "$output" == *"hello_unbounded"* ]]
  # Diagnostic goes to STDERR (merged via 2>&1) — NOT stdout, which is the hook's
  # single-JSON decision channel. Emitting JSON here corrupted the protocol on
  # macOS without coreutils.
  [[ "$output" == *"timeout unavailable"* ]]
}

# ---------------------------------------------------------------------------
# emit_block() and emit_advisory()
# ---------------------------------------------------------------------------

@test "emit_block: outputs valid JSON with decision=block" {
  run bash -c "
    source '$HOOK_LIB'
    emit_block 'MUTATION GATE BLOCKED: test reason'
  "
  [ "$status" -eq 0 ]
  # Must be valid JSON
  echo "$output" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d['decision']=='block'; assert 'MUTATION GATE BLOCKED' in d['reason']"
  [ $? -eq 0 ]
}

@test "emit_advisory: outputs valid JSON with additionalContext" {
  run bash -c "
    source '$HOOK_LIB'
    emit_advisory 'MUTATION GATE ADVISORY: no adapter'
  "
  [ "$status" -eq 0 ]
  echo "$output" | python3 -c "
import json,sys
d=json.load(sys.stdin)
ctx = d['hookSpecificOutput']['additionalContext']
assert 'MUTATION GATE ADVISORY' in ctx
"
  [ $? -eq 0 ]
}

# ---------------------------------------------------------------------------
# is_test_command()
# ---------------------------------------------------------------------------

@test "is_test_command: recognizes npm test" {
  run bash -c "source '$HOOK_LIB'; is_test_command 'npm test'"
  [ "$status" -eq 0 ]
}

@test "is_test_command: recognizes npx vitest run" {
  run bash -c "source '$HOOK_LIB'; is_test_command 'npx vitest run'"
  [ "$status" -eq 0 ]
}

@test "is_test_command: recognizes mvn test" {
  run bash -c "source '$HOOK_LIB'; is_test_command 'mvn test'"
  [ "$status" -eq 0 ]
}

@test "is_test_command: recognizes dotnet test" {
  run bash -c "source '$HOOK_LIB'; is_test_command 'dotnet test'"
  [ "$status" -eq 0 ]
}

@test "is_test_command: rejects echo hello" {
  run bash -c "source '$HOOK_LIB'; is_test_command 'echo hello'"
  [ "$status" -ne 0 ]
}

@test "is_test_command: rejects git status" {
  run bash -c "source '$HOOK_LIB'; is_test_command 'git status'"
  [ "$status" -ne 0 ]
}
