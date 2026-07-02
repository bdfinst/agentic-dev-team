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

@test "wrapper: resolves DOTNET_ROOT via _probe_dotnet_root when unset (rewritten for #564)" {
  # Original test hard-coded /opt/homebrew/opt/dotnet/libexec, which broke on
  # any machine (Linux CI, most non-Homebrew Macs) without that literal path.
  # The new probe is a sourceable function callable with a candidate list.
  # Source the wrapper (its sourced-vs-executed guard suppresses main flow),
  # then call _probe_dotnet_root directly with a fixture whose SDK layout
  # exists on disk. The function's stdout is the resolved path.
  fixture="$HERMETIC_ROOT/fake-installs/probe-default/libexec"
  mkdir -p "$fixture/shared"   # shared/ dir marker satisfies the probe

  # shellcheck disable=SC1090
  source "$WRAPPER"
  run _probe_dotnet_root "$fixture"
  [ "$status" -eq 0 ]
  [ "$output" = "$fixture" ]
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

# =============================================================================
# Issue #564 — _probe_dotnet_root function-level tests
# =============================================================================
#
# The probe function is sourceable; the wrapper's sourced-vs-executed guard
# suppresses the main flow when the file is sourced, so bats can call the
# probe directly with fixture paths. These tests don't invoke the wrapper
# end-to-end — they exercise the pure function.

@test "probe-fn: returns first candidate with executable dotnet" {
  # shellcheck disable=SC1090
  source "$WRAPPER"
  fx="$HERMETIC_ROOT/fx"
  mkdir -p "$fx/a" "$fx/b"
  printf '#!/usr/bin/env bash\nexit 0\n' >"$fx/a/dotnet"
  chmod +x "$fx/a/dotnet"
  run _probe_dotnet_root "$fx/a" "$fx/b"
  [ "$status" -eq 0 ]
  [ "$output" = "$fx/a" ]
}

@test "probe-fn: returns first candidate with dotnet.exe marker (Windows-style)" {
  # #564 Acceptance Critic blocker — dotnet.exe-only marker must count as a
  # hit even when no shared/ dir and no non-.exe dotnet are present.
  # shellcheck disable=SC1090
  source "$WRAPPER"
  fx="$HERMETIC_ROOT/fx"
  mkdir -p "$fx/win"
  printf '#!/usr/bin/env bash\nexit 0\n' >"$fx/win/dotnet.exe"
  chmod +x "$fx/win/dotnet.exe"
  run _probe_dotnet_root "$fx/win"
  [ "$status" -eq 0 ]
  [ "$output" = "$fx/win" ]
}

@test "probe-fn: returns first candidate with shared/ dir marker" {
  # shellcheck disable=SC1090
  source "$WRAPPER"
  fx="$HERMETIC_ROOT/fx"
  mkdir -p "$fx/sdk/shared"
  run _probe_dotnet_root "$fx/sdk"
  [ "$status" -eq 0 ]
  [ "$output" = "$fx/sdk" ]
}

@test "probe-fn: skips empty candidate segments" {
  # Guards against the [ -z "$candidate" ] && continue branch in the loop.
  # shellcheck disable=SC1090
  source "$WRAPPER"
  fx="$HERMETIC_ROOT/fx"
  mkdir -p "$fx/valid/shared"
  run _probe_dotnet_root "" "$fx/valid" ""
  [ "$status" -eq 0 ]
  [ "$output" = "$fx/valid" ]
}

@test "probe-fn: candidate hit order — position 1 wins over position 3" {
  # shellcheck disable=SC1090
  source "$WRAPPER"
  fx="$HERMETIC_ROOT/fx"
  mkdir -p "$fx/homebrew-as/shared" "$fx/debian/shared"
  run _probe_dotnet_root "$fx/homebrew-as" "$fx/homebrew-intel" "$fx/debian"
  [ "$status" -eq 0 ]
  [ "$output" = "$fx/homebrew-as" ]
}

@test "probe-fn: candidate hit order — position 4 wins over position 5" {
  # shellcheck disable=SC1090
  source "$WRAPPER"
  fx="$HERMETIC_ROOT/fx"
  mkdir -p "$fx/fedora/shared" "$fx/user-scope/shared"
  run _probe_dotnet_root "$fx/homebrew-as" "$fx/homebrew-intel" "$fx/debian" "$fx/fedora" "$fx/user-scope"
  [ "$status" -eq 0 ]
  [ "$output" = "$fx/fedora" ]
}

@test "probe-fn: candidate hit order — position 6 wins over position 7" {
  # shellcheck disable=SC1090
  source "$WRAPPER"
  fx="$HERMETIC_ROOT/fx"
  mkdir -p "$fx/win-pf/shared" "$fx/win-lower/shared"
  run _probe_dotnet_root "$fx/nowhere1" "$fx/nowhere2" "$fx/nowhere3" "$fx/nowhere4" "$fx/nowhere5" \
      "$fx/win-pf" "$fx/win-lower"
  [ "$status" -eq 0 ]
  [ "$output" = "$fx/win-pf" ]
}

@test "probe-fn: handles paths with spaces (Windows Program Files style)" {
  # shellcheck disable=SC1090
  source "$WRAPPER"
  fx="$HERMETIC_ROOT/fx/Program Files/dotnet"
  mkdir -p "$fx/shared"
  run _probe_dotnet_root "$fx"
  [ "$status" -eq 0 ]
  [ "$output" = "$fx" ]
}

@test "probe-fn: returns exit 1 when no candidate hits" {
  # shellcheck disable=SC1090
  source "$WRAPPER"
  run _probe_dotnet_root "$HERMETIC_ROOT/nope-1" "$HERMETIC_ROOT/nope-2"
  [ "$status" -eq 1 ]
  [ -z "$output" ]
}

# =============================================================================
# Issue #564 — wrapper-level tests for PATH fallback and exit-3 no-SDK path
# =============================================================================

# The wrapper-level probe-miss + exit-3 tests below require the host to
# have NO .NET SDK installed at any of the 7 documented probe paths — an
# invariant we can only assert on CI runners (which don't ship a Homebrew
# .NET). Local dev machines with a real /opt/homebrew/opt/dotnet/libexec
# install skip these end-to-end tests; the function-level probe tests above
# already cover the probe's behavioral contract deterministically. This is
# the tradeoff the design chose (no public probe-override surface) — see
# plan Risks & Open Questions.
_any_real_dotnet_probe_path_present() {
  local candidate
  for candidate in \
      /opt/homebrew/opt/dotnet/libexec \
      /usr/local/opt/dotnet/libexec \
      /usr/share/dotnet \
      /usr/lib/dotnet \
      "${HOME}/.dotnet" \
      "/c/Program Files/dotnet" \
      "/c/program files/dotnet"; do
    if [ -x "$candidate/dotnet" ] \
        || [ -x "$candidate/dotnet.exe" ] \
        || [ -d "$candidate/shared" ]; then
      return 0
    fi
  done
  return 1
}

@test "wrapper: falls back to dirname \$(command -v dotnet) when no probe candidate hits" {
  if _any_real_dotnet_probe_path_present; then
    skip "host has a real .NET SDK at a documented probe path — probe short-circuits before the PATH fallback"
  fi
  unset DOTNET_ROOT
  run "$WRAPPER"
  [ "$status" -eq 0 ]
  # DOTNET_ROOT recorded in invocation-03 should be $FAKE_BIN (dirname of
  # $FAKE_BIN/dotnet, which is what command -v resolves to).
  grep -q "^DOTNET_ROOT=$FAKE_BIN$" "$RECORD_DIR/invocation-03"
}

@test "wrapper: exits 3 when probe misses AND dotnet not on PATH" {
  if _any_real_dotnet_probe_path_present; then
    skip "host has a real .NET SDK at a documented probe path — probe short-circuits before the exit-3 path"
  fi
  unset DOTNET_ROOT
  PATH=/usr/bin:/bin run "$WRAPPER"
  [ "$status" -eq 3 ]
  # No .sln mutation.
  [ -f "$SLN" ]
  [ ! -f "${SLN}.stryker-hidden" ]
  # No dotnet build invocations recorded.
  [ ! -f "$RECORD_DIR/invocation-01" ]
}

@test "wrapper: exit-3 stderr names at least one probed path" {
  if _any_real_dotnet_probe_path_present; then
    skip "host has a real .NET SDK at a documented probe path — exit-3 unreachable"
  fi
  unset DOTNET_ROOT
  PATH=/usr/bin:/bin run "$WRAPPER"
  [ "$status" -eq 3 ]
  # At least one of the documented probe candidates named in stderr.
  echo "$stderr$output" | grep -qE "(/opt/homebrew/opt/dotnet|/usr/share/dotnet|Program Files/dotnet)"
}

@test "wrapper: exit-3 stderr instructs setting DOTNET_ROOT explicitly" {
  if _any_real_dotnet_probe_path_present; then
    skip "host has a real .NET SDK at a documented probe path — exit-3 unreachable"
  fi
  unset DOTNET_ROOT
  PATH=/usr/bin:/bin run "$WRAPPER"
  [ "$status" -eq 3 ]
  echo "$stderr$output" | grep -qi "set.*DOTNET_ROOT"
}

@test "wrapper: exit-3 stderr includes dotnet.microsoft.com/download URL" {
  if _any_real_dotnet_probe_path_present; then
    skip "host has a real .NET SDK at a documented probe path — exit-3 unreachable"
  fi
  unset DOTNET_ROOT
  PATH=/usr/bin:/bin run "$WRAPPER"
  [ "$status" -eq 3 ]
  echo "$stderr$output" | grep -q "dotnet.microsoft.com/download"
}

# =============================================================================
# Issue #564 — source-lint tests on wrapper header comment
# =============================================================================

@test "wrapper source-lint: header declares cross-platform DOTNET_ROOT scope" {
  run head -20 "$WRAPPER"
  [ "$status" -eq 0 ]
  echo "$output" | grep -q "macOS"
  echo "$output" | grep -qi "linux"
  echo "$output" | grep -qi "Windows Git Bash"
}

@test "wrapper source-lint: header does NOT contain 'not a supported target'" {
  run grep -i "not a supported target" "$WRAPPER"
  [ "$status" -ne 0 ]
}

@test "wrapper source-lint: header names the Windows signal-handling follow-up issue" {
  # Grep for a #NNN reference OR a github.com/.../issues/NNN URL — matches
  # either the short-form issue link or a full URL.
  run head -30 "$WRAPPER"
  [ "$status" -eq 0 ]
  echo "$output" | grep -qE "(#[0-9]+|issues/[0-9]+)"
}

@test "wrapper source-lint: default probe list contains all 7 documented filesystem candidates" {
  # The wrapper source names each of the 7 default candidates in its callsite.
  # PATH fallback is a separate code path and is NOT counted here.
  grep -qF "/opt/homebrew/opt/dotnet/libexec" "$WRAPPER"
  grep -qF "/usr/local/opt/dotnet/libexec"    "$WRAPPER"
  grep -qF "/usr/share/dotnet"                "$WRAPPER"
  grep -qF "/usr/lib/dotnet"                  "$WRAPPER"
  grep -qF ".dotnet"                          "$WRAPPER"
  grep -qF "/c/Program Files/dotnet"          "$WRAPPER"
  grep -qF "/c/program files/dotnet"          "$WRAPPER"
}
