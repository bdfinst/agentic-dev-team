#!/usr/bin/env bats
# Unit tests for csharp-stryker-net-status-loop.sh (issue #558).
#
# The loop is decomposed into pure functions callable in isolation:
#   status_loop_start LOGFILE INTERVAL COMPILE_THRESHOLD STRYKER_PID
#     — the ticking loop, backgrounded by the wrapper.
#   emit_status_line LOGFILE
#     — parses log tail and prints one status record to stdout.
#   check_red_flags LOGFILE COMPILE_THRESHOLD STRYKER_PID
#     — pure(-ish) function: reads log + PID liveness, prints zero or more
#       [RED-FLAG] lines to stdout. Drift counter kept in a file under
#       $STATUS_LOOP_STATE_DIR (default $TMPDIR) keyed on STRYKER_PID.
#
# Fixtures under tests/fixtures/stryker-net-logs/ cover each documented
# failure mode plus the healthy case.
#
# Plan: plans/mutation-testing-net-silent-failure-hardening.md — Slice 4.

LOOP="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/mutation-testing/scripts/csharp-stryker-net-status-loop.sh"
FIXTURES="$BATS_TEST_DIRNAME/../fixtures/stryker-net-logs"

setup() {
  # Per-test drift-counter state dir so counter runs don't leak across tests.
  STATUS_LOOP_STATE_DIR="$(mktemp -d -t "loop-state-$$-XXXXXX")"
  export STATUS_LOOP_STATE_DIR
  # A parent PID we can be sure is alive (the bats runner).
  export ALIVE_PID=$$
  # A PID we can be sure is NOT alive (fork+exit).
  bash -c 'exit 0' &
  DEAD_PID=$!
  wait "$DEAD_PID" 2>/dev/null || true
  export DEAD_PID
}

teardown() {
  if [ -n "${STATUS_LOOP_STATE_DIR:-}" ] && [ -d "$STATUS_LOOP_STATE_DIR" ]; then
    case "$STATUS_LOOP_STATE_DIR" in
      /tmp/*|/var/folders/*|/private/var/folders/*|/private/tmp/*)
        rm -rf "$STATUS_LOOP_STATE_DIR"
        ;;
    esac
  fi
}

# =============================================================================
# Loop source: shellcheck
# =============================================================================

@test "status-loop: file exists" {
  [ -f "$LOOP" ]
}

@test "status-loop: passes shellcheck" {
  if ! command -v shellcheck >/dev/null 2>&1; then
    skip "shellcheck not installed"
  fi
  run shellcheck "$LOOP"
  [ "$status" -eq 0 ]
}

# =============================================================================
# emit_status_line — one line per tick, documented fields
# =============================================================================

@test "emit_status_line: healthy dots log produces one line with kills/survived/timeout/elapsed" {
  # shellcheck disable=SC1090
  source "$LOOP"
  run emit_status_line "$FIXTURES/healthy-dots.log"
  [ "$status" -eq 0 ]
  # One line only.
  [ "$(printf '%s' "$output" | wc -l | awk '{print $1}')" -le 1 ]
  # Named fields present.
  echo "$output" | grep -q "killed"
  echo "$output" | grep -q "survived"
  echo "$output" | grep -q "timeout"
  echo "$output" | grep -q "elapsed"
}

@test "emit_status_line: counts dots-tested from log (survives redirection)" {
  # shellcheck disable=SC1090
  source "$LOOP"
  run emit_status_line "$FIXTURES/healthy-dots.log"
  [ "$status" -eq 0 ]
  # Healthy fixture has 57 dots after the "Testing mutants:" marker.
  # The status line must report a mutants-tested count derived from that,
  # not from the summary block (the loop needs to work mid-run, before
  # the summary is written).
  echo "$output" | grep -qE "tested"
}

# =============================================================================
# check_red_flags — per fixture
# =============================================================================

@test "check_red_flags: healthy fixture emits nothing" {
  # shellcheck disable=SC1090
  source "$LOOP"
  run check_red_flags "$FIXTURES/healthy-dots.log" 25 "$ALIVE_PID"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "check_red_flags: Killed==0 && Survived>0 emits red-flag referencing #554" {
  # shellcheck disable=SC1090
  source "$LOOP"
  run check_red_flags "$FIXTURES/mutation-switch-broken.log" 25 "$ALIVE_PID"
  [ "$status" -eq 0 ]
  echo "$output" | grep -q "\[RED-FLAG\]"
  echo "$output" | grep -q "mutation-switch"
  echo "$output" | grep -q "#554"
}

@test "check_red_flags: CompileError count strictly ABOVE threshold trips flag" {
  # shellcheck disable=SC1090
  source "$LOOP"
  run check_red_flags "$FIXTURES/compile-error-above.log" 25 "$ALIVE_PID"
  [ "$status" -eq 0 ]
  echo "$output" | grep -q "\[RED-FLAG\]"
  echo "$output" | grep -q "CompileError"
  # Line names the observed count (26) and the threshold (25).
  echo "$output" | grep -qE "26.*25|threshold.*25.*26|CompileError.*26"
}

@test "check_red_flags: CompileError count AT threshold does NOT trip flag" {
  # shellcheck disable=SC1090
  source "$LOOP"
  run check_red_flags "$FIXTURES/compile-error-at.log" 25 "$ALIVE_PID"
  [ "$status" -eq 0 ]
  # No CompileError red-flag when count == threshold. (Other red flags
  # might fire from unrelated content — but the compile-error-at fixture
  # was authored not to trip them.)
  echo "$output" | grep -v "CompileError" >/dev/null 2>&1 || [ -z "$output" ]
  # Simpler assertion: no line containing "CompileError" in output.
  ! echo "$output" | grep -q "CompileError"
}

@test "check_red_flags: SolutionPath naming unexpected .sln trips flag referencing #557" {
  # shellcheck disable=SC1090
  source "$LOOP"
  # The trap fixture names two test-project dlls under SolutionPath. The
  # loop consults $STATUS_LOOP_EXPECTED_TARGET (if set) to know what's
  # expected — anything else is unexpected. Here we pin the expected one
  # so the other one is the trap.
  export STATUS_LOOP_EXPECTED_TARGET="Foo.Tests.Mutation"
  run check_red_flags "$FIXTURES/solution-path-trap.log" 25 "$ALIVE_PID"
  [ "$status" -eq 0 ]
  echo "$output" | grep -q "\[RED-FLAG\]"
  echo "$output" | grep -q "SolutionPath"
  echo "$output" | grep -q "#557"
}

@test "check_red_flags: dead Stryker PID (no completion marker) trips flag referencing #558" {
  # shellcheck disable=SC1090
  source "$LOOP"
  run check_red_flags "$FIXTURES/truncated-dead-process.log" 25 "$DEAD_PID"
  [ "$status" -eq 0 ]
  echo "$output" | grep -q "\[RED-FLAG\]"
  echo "$output" | grep -q "Stryker.*died\|Stryker process died"
  echo "$output" | grep -q "#558"
}

@test "check_red_flags: dead Stryker PID with completion marker does NOT trip died-flag" {
  # A completed successful run leaves the PID reaped by `wait`; that's
  # normal, not a red flag. Healthy log includes "The final mutation score"
  # completion marker.
  # shellcheck disable=SC1090
  source "$LOOP"
  run check_red_flags "$FIXTURES/healthy-dots.log" 25 "$DEAD_PID"
  [ "$status" -eq 0 ]
  ! echo "$output" | grep -q "Stryker.*died"
}

# =============================================================================
# Parser-drift catch-all — N consecutive unrecognized ticks
# =============================================================================

@test "check_red_flags: 1st and 2nd unrecognized ticks do NOT trip drift flag" {
  # shellcheck disable=SC1090
  source "$LOOP"

  run check_red_flags "$FIXTURES/unrecognized.log" 25 "$ALIVE_PID"
  [ "$status" -eq 0 ]
  ! echo "$output" | grep -q "parser drift"

  run check_red_flags "$FIXTURES/unrecognized.log" 25 "$ALIVE_PID"
  [ "$status" -eq 0 ]
  ! echo "$output" | grep -q "parser drift"
}

@test "check_red_flags: 3rd consecutive unrecognized tick trips parser-drift flag referencing #558" {
  # shellcheck disable=SC1090
  source "$LOOP"

  check_red_flags "$FIXTURES/unrecognized.log" 25 "$ALIVE_PID" >/dev/null
  check_red_flags "$FIXTURES/unrecognized.log" 25 "$ALIVE_PID" >/dev/null
  run check_red_flags "$FIXTURES/unrecognized.log" 25 "$ALIVE_PID"
  [ "$status" -eq 0 ]
  echo "$output" | grep -q "\[RED-FLAG\]"
  echo "$output" | grep -q "parser drift"
  echo "$output" | grep -q "#558"
}

@test "check_red_flags: drift counter resets when a recognized tick is observed" {
  # shellcheck disable=SC1090
  source "$LOOP"

  # Two unrecognized ticks.
  check_red_flags "$FIXTURES/unrecognized.log" 25 "$ALIVE_PID" >/dev/null
  check_red_flags "$FIXTURES/unrecognized.log" 25 "$ALIVE_PID" >/dev/null
  # A recognized tick — should reset the drift counter.
  check_red_flags "$FIXTURES/healthy-dots.log" 25 "$ALIVE_PID" >/dev/null
  # Now two more unrecognized — should NOT trip yet (counter was reset).
  run check_red_flags "$FIXTURES/unrecognized.log" 25 "$ALIVE_PID"
  [ "$status" -eq 0 ]
  ! echo "$output" | grep -q "parser drift"
  run check_red_flags "$FIXTURES/unrecognized.log" 25 "$ALIVE_PID"
  [ "$status" -eq 0 ]
  ! echo "$output" | grep -q "parser drift"
}
