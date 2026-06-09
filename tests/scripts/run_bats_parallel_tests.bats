#!/usr/bin/env bats
# run-bats-parallel.sh — portable across-file bats fan-out (xargs -P, no GNU
# `parallel`). These tests pin its orchestration contract — file discovery,
# parallel fan-out, and collect-all-failures exit semantics.
#
# They drive the runner with a STUB `bats` placed on PATH rather than nesting a
# real bats inside this bats run. Nesting real bats is fragile across versions
# (the inner process inherits the outer's test-selection state), and we only
# need to verify the runner's own logic, not bats itself. The stub reports
# which file it "ran" and fails iff the path is marked to fail.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
RUNNER="$REPO_ROOT/scripts/run-bats-parallel.sh"

setup() {
  WORK="$(mktemp -d)"

  # Stub `bats`: echo the file it ran, exit non-zero iff the name says "fail".
  STUB="$WORK/bin"
  mkdir -p "$STUB"
  cat > "$STUB/bats" <<'EOF'
#!/usr/bin/env bash
echo "ran:$1"
case "$1" in *fail*) exit 1 ;; *) exit 0 ;; esac
EOF
  chmod +x "$STUB/bats"

  # Fixture files only need to exist with a .bats suffix; the stub ignores
  # their contents. Two passing, one failing.
  SUITE="$WORK/suite"
  mkdir -p "$SUITE"
  : > "$SUITE/pass_a.bats"
  : > "$SUITE/pass_b.bats"
  : > "$SUITE/fail_c.bats"
}

teardown() {
  [ -n "${WORK:-}" ] && rm -rf "$WORK"
}

# Run the real runner with the stub bats taking precedence on PATH.
run_runner() {
  run env PATH="$STUB:$PATH" bash "$RUNNER" "$@"
}

@test "all files pass -> exit 0" {
  run_runner -j 2 "$SUITE/pass_a.bats" "$SUITE/pass_b.bats"
  [ "$status" -eq 0 ]
}

@test "any file fails -> non-zero exit" {
  run_runner -j 2 "$SUITE/pass_a.bats" "$SUITE/fail_c.bats"
  [ "$status" -ne 0 ]
}

@test "collect-all-failures: a failing file does not abort the others" {
  # Both the passing and the failing file must have executed.
  run_runner -j 2 "$SUITE/pass_a.bats" "$SUITE/fail_c.bats"
  [ "$status" -ne 0 ]
  echo "$output" | grep -q "ran:.*pass_a.bats"
  echo "$output" | grep -q "ran:.*fail_c.bats"
}

@test "directory args expand to their .bats files" {
  run_runner -j 2 "$SUITE"
  # The dir holds two passing + one failing file -> overall non-zero, all ran.
  [ "$status" -ne 0 ]
  echo "$output" | grep -q "ran:.*pass_a.bats"
  echo "$output" | grep -q "ran:.*pass_b.bats"
  echo "$output" | grep -q "ran:.*fail_c.bats"
}

@test "no .bats files -> exit 0 with a message (nothing to run is not a failure)" {
  local empty
  empty="$(mktemp -d)"
  run_runner "$empty"
  [ "$status" -eq 0 ]
  echo "$output" | grep -q "no .bats files found"
  rm -rf "$empty"
}

@test "JOBS defaults sanely when -j is omitted (still runs)" {
  run_runner "$SUITE/pass_a.bats"
  [ "$status" -eq 0 ]
  echo "$output" | grep -q "ran:.*pass_a.bats"
}
