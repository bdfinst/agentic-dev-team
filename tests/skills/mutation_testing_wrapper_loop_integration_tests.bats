#!/usr/bin/env bats
# End-to-end integration test: wrapper + status-loop together.
# Complements the pure-function unit tests in
# mutation_testing_status_loop_tests.bats and the STATUS_INTERVAL=0 wrapper
# tests in mutation_testing_wrapper_tests.bats.
#
# Plan: plans/mutation-testing-net-silent-failure-hardening.md — Slice 4 Step 4.2.

load '../lib/hermetic'

WRAPPER="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/mutation-testing/scripts/csharp-stryker-net-wrapper.sh"

setup() {
  hermetic_setup

  export RECORD_DIR="$HERMETIC_ROOT/record"
  mkdir -p "$RECORD_DIR"

  export FAKE_BIN="$HERMETIC_ROOT/bin"
  mkdir -p "$FAKE_BIN"

  # Fake dotnet — writes a scripted log to $LOGFILE tracking a bad Stryker
  # run (Killed:0 + Survived:100). The build steps just exit 0. The stryker
  # invocation writes the bad-summary log, then sleeps briefly so the loop
  # ticks at least once and sees the red-flag pattern, then exits 0.
  cat >"$FAKE_BIN/dotnet" <<'FAKE_EOF'
#!/usr/bin/env bash
if [ "${1:-}" = "build" ]; then
    exit 0
fi
if [ "${1:-}" = "stryker" ]; then
    # Write the bad-Stryker log directly to stdout, which the wrapper redirects
    # to $LOGFILE.
    cat <<'LOG_EOF'
Stryker.NET v4.7.0

[13:20:14 INF] Analyzing project 'Foo.Tests.csproj'
Testing mutants:
....................................................................................................
Killed:      0
Survived:  100
Timeout:     0
No coverage: 0
LOG_EOF
    # Sleep so the status loop has enough time to tick at least once against
    # a stable log file.
    sleep 2
    exit 0
fi
exit 0
FAKE_EOF
  chmod +x "$FAKE_BIN/dotnet"
  export PATH="$FAKE_BIN:$PATH"

  # STRYKER_BIN → dotnet stryker (same shim as the unit tests).
  export STRYKER_BIN="dotnet-stryker-integration-fake"
  cat >"$FAKE_BIN/$STRYKER_BIN" <<'FAKE_EOF'
#!/usr/bin/env bash
exec dotnet stryker "$@"
FAKE_EOF
  chmod +x "$FAKE_BIN/$STRYKER_BIN"

  echo "solution stub" >"$HERMETIC_ROOT/Foo.sln"
  export SLN="$HERMETIC_ROOT/Foo.sln"
  export SHIM_PROJECT=""
  export LOGFILE="$HERMETIC_ROOT/wrapper.log"

  # Loop with a 1s cadence so it ticks quickly, and a small drift threshold
  # so we don't wait forever. Isolate loop state to this test's tempdir.
  export STATUS_LOOP_STATE_DIR="$HERMETIC_ROOT/loop-state"
  mkdir -p "$STATUS_LOOP_STATE_DIR"
}

teardown() {
  hermetic_teardown
}

@test "wrapper + loop: red-flag fires on Killed:0 + Survived>0 pattern" {
  # Backgrounded so stderr can be captured to a file; then wait for exit.
  # Status loop writes to stderr from the wrapper's perspective (the loop's
  # stdout is inherited by the wrapper's stderr since Stryker's stdout was
  # already redirected to $LOGFILE with `> "$LOGFILE" 2>&1`).
  #
  # Actually: the wrapper backgrounds Stryker with `>"$LOGFILE" 2>&1`, but the
  # status loop is a separate background — its stdout goes to the wrapper's
  # stdout, which we capture here.
  STATUS_INTERVAL=1 "$WRAPPER" stryker >"$HERMETIC_ROOT/wrapper-stdout" 2>"$HERMETIC_ROOT/wrapper-stderr"
  status=$?

  # Wrapper's own exit is 0 (Stryker exited 0). Loop-detected red flag
  # doesn't fail the run — it's an observability signal.
  [ "$status" -eq 0 ]

  # Some tick's output must include a RED-FLAG referencing #554.
  {
    cat "$HERMETIC_ROOT/wrapper-stdout" 2>/dev/null
    cat "$HERMETIC_ROOT/wrapper-stderr" 2>/dev/null
  } | grep -q "\[RED-FLAG\]"
  {
    cat "$HERMETIC_ROOT/wrapper-stdout" 2>/dev/null
    cat "$HERMETIC_ROOT/wrapper-stderr" 2>/dev/null
  } | grep -q "#554"
}

@test "wrapper + loop: STATUS_INTERVAL=0 disables loop (no status output)" {
  # With the loop disabled, the wrapper's stdout should carry no [RED-FLAG]
  # lines and no "tested=" status records — even though the log would trip
  # them if the loop were running.
  STATUS_INTERVAL=0 "$WRAPPER" stryker >"$HERMETIC_ROOT/wrapper-stdout" 2>"$HERMETIC_ROOT/wrapper-stderr"

  ! grep -q "\[RED-FLAG\]" "$HERMETIC_ROOT/wrapper-stdout" "$HERMETIC_ROOT/wrapper-stderr"
  ! grep -q "^tested=" "$HERMETIC_ROOT/wrapper-stdout" "$HERMETIC_ROOT/wrapper-stderr"
}
