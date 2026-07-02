#!/usr/bin/env bats
# Contract tests for csharp-stryker-net-wrapper.sh (issue #559).
#
# Fixture strategy: temp repo with a dummy .sln + a fake `dotnet` shim on
# PATH that records arg vectors, invocation timestamps, and env vars into
# $RECORD_DIR/. The shim's exit code is controlled by env sentinels so we
# can drive normal / non-zero / signal-trapped paths.
#
# STATUS_INTERVAL=0 is pinned throughout this file — the loop-integration
# path is exercised by mutation_testing_wrapper_loop_integration_tests.bats
# (Slice 4 Step 4.2), which requires csharp-stryker-net-status-loop.sh to
# exist.
#
# Plan: plans/mutation-testing-net-silent-failure-hardening.md — Slice 3.

load '../lib/hermetic'

WRAPPER="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/mutation-testing/scripts/csharp-stryker-net-wrapper.sh"

setup() {
  hermetic_setup
  export STATUS_INTERVAL=0

  # Fake `dotnet` shim on PATH. Records argv + env + wall-clock timestamp
  # per invocation into $RECORD_DIR. Behavior toggled by env sentinels.
  export RECORD_DIR="$HERMETIC_ROOT/record"
  mkdir -p "$RECORD_DIR"

  export FAKE_BIN="$HERMETIC_ROOT/bin"
  mkdir -p "$FAKE_BIN"
  # Fake `dotnet` shim — records every invocation to $RECORD_DIR and dispatches
  # on $1 (build vs stryker) via env sentinels. Storing argv with a tab
  # separator (not %q) keeps the recorded form searchable with plain grep.
  cat >"$FAKE_BIN/dotnet" <<'FAKE_EOF'
#!/usr/bin/env bash
n="$(ls "$RECORD_DIR" 2>/dev/null | wc -l | awk '{print $1}')"
n=$((n + 1))
rec="$RECORD_DIR/invocation-$(printf '%02d' "$n")"
{
  printf 'ts_ns=%s\n' "$(date +%s%N 2>/dev/null || python3 -c 'import time;print(int(time.time()*1e9))')"
  printf 'DOTNET_ROOT=%s\n' "${DOTNET_ROOT:-}"
  printf 'PWD=%s\n' "$PWD"
  printf 'argc=%d\n' "$#"
  i=0
  for a in "$@"; do
    i=$((i + 1))
    printf 'arg[%d]=%s\n' "$i" "$a"
  done
} >"$rec"

if [ "${1:-}" = "build" ]; then
    exit 0
fi
if [ "${1:-}" = "stryker" ]; then
    if [ -n "${FAKE_STRYKER_EXIT_CODE:-}" ]; then
        exit "$FAKE_STRYKER_EXIT_CODE"
    fi
    if [ -n "${FAKE_STRYKER_BLOCK_SENTINEL:-}" ]; then
        echo $$ >"$RECORD_DIR/stryker.pid"
        trap 'exit 130' INT
        trap 'exit 143' TERM
        while [ -e "$FAKE_STRYKER_BLOCK_SENTINEL" ]; do
            sleep 0.1 &
            wait $!
        done
        exit 0
    fi
    exit 0
fi
exit 0
FAKE_EOF
  chmod +x "$FAKE_BIN/dotnet"
  export PATH="$FAKE_BIN:$PATH"

  # A dummy .sln + shim project the wrapper is configured to pre-build.
  echo "solution stub" >"$HERMETIC_ROOT/Foo.sln"
  mkdir -p "$HERMETIC_ROOT/tests/Foo.Tests.Mutation"
  cat >"$HERMETIC_ROOT/tests/Foo.Tests.Mutation/Foo.Tests.Mutation.csproj" <<'EOF'
<Project Sdk="Microsoft.NET.Sdk" />
EOF

  export SLN="$HERMETIC_ROOT/Foo.sln"
  export SHIM_PROJECT="$HERMETIC_ROOT/tests/Foo.Tests.Mutation/Foo.Tests.Mutation.csproj"
  export STRYKER_BIN="dotnet-stryker-wrapper-fake"
  # STRYKER_BIN isn't executable; wrapper invokes it via `dotnet stryker` path.
  # Wrapper implementation calls "$STRYKER_BIN" — we alias it to our fake.
  cat >"$FAKE_BIN/$STRYKER_BIN" <<'FAKE_EOF'
#!/usr/bin/env bash
exec dotnet stryker "$@"
FAKE_EOF
  chmod +x "$FAKE_BIN/$STRYKER_BIN"

  export LOGFILE="$HERMETIC_ROOT/wrapper.log"
}

teardown() {
  hermetic_teardown
}

# =============================================================================
# Wrapper source: shellcheck + static-lint guardrails
# =============================================================================

@test "wrapper: file exists and is executable" {
  [ -f "$WRAPPER" ]
  [ -x "$WRAPPER" ]
}

@test "wrapper: passes shellcheck" {
  if ! command -v shellcheck >/dev/null 2>&1; then
    skip "shellcheck not installed"
  fi
  run shellcheck "$WRAPPER"
  [ "$status" -eq 0 ]
}

@test "wrapper: never pipes Stryker output to bare | tee" {
  # #550 lint — a bare pipe to tee masks the tool's exit code.
  run grep -n -E '\$STRYKER_BIN.*\|[[:space:]]*tee' "$WRAPPER"
  [ "$status" -ne 0 ]
}

# =============================================================================
# Wrapper behavior: pre-build ordering
# =============================================================================

@test "wrapper: builds SLN and SHIM_PROJECT before hiding .sln" {
  run "$WRAPPER"
  [ "$status" -eq 0 ]

  # Timeline: invocation-01 = dotnet build $SLN, invocation-02 = dotnet build
  # $SHIM_PROJECT, invocation-03 = dotnet stryker. The recorded arg[1]=... /
  # arg[2]=... format survives whitespace and glob characters unmodified.
  grep -q "^arg\[1\]=build$" "$RECORD_DIR/invocation-01"
  grep -q "Foo.sln" "$RECORD_DIR/invocation-01"

  grep -q "^arg\[1\]=build$" "$RECORD_DIR/invocation-02"
  grep -q "Foo.Tests.Mutation" "$RECORD_DIR/invocation-02"

  grep -q "^arg\[1\]=stryker$" "$RECORD_DIR/invocation-03"
}

# =============================================================================
# Wrapper behavior: .sln trap-restore
# =============================================================================

@test "wrapper: restores .sln on normal exit" {
  run "$WRAPPER"
  [ "$status" -eq 0 ]
  [ -f "$SLN" ]
  [ ! -f "${SLN}.stryker-hidden" ]
  # Content preserved.
  run cat "$SLN"
  [ "$output" = "solution stub" ]
}

@test "wrapper: restores .sln when Stryker exits non-zero" {
  FAKE_STRYKER_EXIT_CODE=42 run "$WRAPPER"
  [ "$status" -eq 42 ]
  [ -f "$SLN" ]
  [ ! -f "${SLN}.stryker-hidden" ]
}

@test "wrapper: restores .sln on SIGINT (tty-Ctrl-C, delivered to process group)" {
  # SIGINT semantics: a tty Ctrl-C delivers SIGINT to the whole foreground
  # process group, not just the wrapper. Simulate by launching the wrapper
  # via `setsid`-style new process group and signalling the group.
  #
  # Note: `kill -INT $wrapper_pid` alone (single-process delivery) does NOT
  # trigger bash's INT trap for a background job — bash background jobs
  # ignore SIGINT delivered outside their controlling tty. That's why the
  # test uses group-delivery via -PGID.
  sentinel="$HERMETIC_ROOT/block"
  touch "$sentinel"
  # Launch wrapper in its own process group so we can group-signal it.
  set -m
  FAKE_STRYKER_BLOCK_SENTINEL="$sentinel" "$WRAPPER" &
  wrapper_pid=$!
  set +m

  # Wait for fake Stryker to be running.
  for _ in $(seq 1 100); do
    [ -f "$RECORD_DIR/stryker.pid" ] && break
    sleep 0.05
  done
  [ -f "$RECORD_DIR/stryker.pid" ]

  # Deliver SIGINT to the wrapper's process group (mimics tty Ctrl-C).
  kill -INT -"$wrapper_pid" 2>/dev/null || kill -INT "$wrapper_pid"
  wait "$wrapper_pid" 2>/dev/null || true

  [ -f "$SLN" ]
  [ ! -f "${SLN}.stryker-hidden" ]
}

@test "wrapper: restores .sln on SIGTERM mid-run" {
  sentinel="$HERMETIC_ROOT/block"
  touch "$sentinel"
  FAKE_STRYKER_BLOCK_SENTINEL="$sentinel" "$WRAPPER" &
  wrapper_pid=$!

  for _ in $(seq 1 100); do
    [ -f "$RECORD_DIR/stryker.pid" ] && break
    sleep 0.05
  done
  [ -f "$RECORD_DIR/stryker.pid" ]

  kill -TERM "$wrapper_pid"
  wait "$wrapper_pid" 2>/dev/null || true

  [ -f "$SLN" ]
  [ ! -f "${SLN}.stryker-hidden" ]
}

# =============================================================================
# Wrapper behavior: SIGINT/SIGTERM also kill the backgrounded Stryker PID
# =============================================================================

@test "wrapper: SIGINT (process group) kills backgrounded Stryker (no orphan)" {
  # SIGINT delivered to the wrapper's process group — mimics tty Ctrl-C.
  # In this case Stryker (a group member) receives SIGINT directly AND the
  # wrapper's trap fires; restore_sln also kills STRYKER_PID as a belt-and-
  # braces measure. Either mechanism reaping the child satisfies the test.
  sentinel="$HERMETIC_ROOT/block"
  touch "$sentinel"
  set -m
  FAKE_STRYKER_BLOCK_SENTINEL="$sentinel" "$WRAPPER" &
  wrapper_pid=$!
  set +m

  for _ in $(seq 1 100); do
    [ -f "$RECORD_DIR/stryker.pid" ] && break
    sleep 0.05
  done
  stryker_pid="$(cat "$RECORD_DIR/stryker.pid")"

  kill -INT -"$wrapper_pid" 2>/dev/null || kill -INT "$wrapper_pid"
  wait "$wrapper_pid" 2>/dev/null || true

  # Give the OS a moment to reap the signalled child.
  for _ in $(seq 1 50); do
    kill -0 "$stryker_pid" 2>/dev/null || break
    sleep 0.05
  done
  run kill -0 "$stryker_pid"
  [ "$status" -ne 0 ]

  rm -f "$sentinel"
}

@test "wrapper: SIGTERM kills backgrounded Stryker (no orphan)" {
  sentinel="$HERMETIC_ROOT/block"
  touch "$sentinel"
  FAKE_STRYKER_BLOCK_SENTINEL="$sentinel" "$WRAPPER" &
  wrapper_pid=$!

  for _ in $(seq 1 100); do
    [ -f "$RECORD_DIR/stryker.pid" ] && break
    sleep 0.05
  done
  stryker_pid="$(cat "$RECORD_DIR/stryker.pid")"

  kill -TERM "$wrapper_pid"
  wait "$wrapper_pid" 2>/dev/null || true

  for _ in $(seq 1 50); do
    kill -0 "$stryker_pid" 2>/dev/null || break
    sleep 0.05
  done
  run kill -0 "$stryker_pid"
  [ "$status" -ne 0 ]

  rm -f "$sentinel"
}

# =============================================================================
# Wrapper behavior: stale hidden .sln refuse (idempotency, deterministic)
# =============================================================================

@test "wrapper: refuses with exit 2 when stale .sln.stryker-hidden coexists with fresh .sln" {
  # Pre-create the stale hidden file.
  cp "$SLN" "${SLN}.stryker-hidden"

  run "$WRAPPER"
  [ "$status" -eq 2 ]
  # Error message names the stale path.
  echo "$output" | grep -q "${SLN}.stryker-hidden"
  # Fresh .sln untouched.
  [ -f "$SLN" ]
  run cat "$SLN"
  [ "$output" = "solution stub" ]
  # No new invocations recorded (refusal was before build/hide).
  ! [ -f "$RECORD_DIR/invocation-01" ]
}

# =============================================================================
# Wrapper behavior: DOTNET_ROOT + args forwarding
# =============================================================================

@test "wrapper: respects a pre-set DOTNET_ROOT" {
  DOTNET_ROOT=/custom/dotnet run "$WRAPPER"
  [ "$status" -eq 0 ]
  grep -q "DOTNET_ROOT=/custom/dotnet" "$RECORD_DIR/invocation-03"
}

@test "wrapper: exports the default DOTNET_ROOT when unset" {
  unset DOTNET_ROOT
  run "$WRAPPER"
  [ "$status" -eq 0 ]
  grep -q "DOTNET_ROOT=/opt/homebrew/opt/dotnet/libexec" "$RECORD_DIR/invocation-03"
}

@test "wrapper: forwards arguments to Stryker unchanged" {
  run "$WRAPPER" --mutate '**/Foo.cs' -O StrykerOutput/probe
  [ "$status" -eq 0 ]
  # Invocation-03 is the Stryker call — the dotnet-stryker shim prepends
  # 'stryker' as arg[1], so user args land at arg[2]..arg[5]. Assert on
  # exact values (arg[N]=VALUE record format preserves globs literally).
  grep -q "^arg\[1\]=stryker$"           "$RECORD_DIR/invocation-03"
  grep -q "^arg\[2\]=--mutate$"          "$RECORD_DIR/invocation-03"
  grep -q "^arg\[3\]=\*\*/Foo.cs$"       "$RECORD_DIR/invocation-03"
  grep -q "^arg\[4\]=-O$"                "$RECORD_DIR/invocation-03"
  grep -q "^arg\[5\]=StrykerOutput/probe$" "$RECORD_DIR/invocation-03"
}
