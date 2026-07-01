#!/usr/bin/env bats
# Post-hook ref-integrity guard in .husky/pre-push — issue #546.
#
# Runs the shipped .husky/pre-push against a scratch repo (isolated via
# hermetic_setup). Only scripts/ci-local.sh is shadowed with a per-scenario
# stub that induces the ref-mutation-or-not the scenario needs; the hook
# itself is the shipped artifact so the test verifies the actual guard,
# not a reimplementation.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
REAL_HOOK="$REPO_ROOT/.husky/pre-push"

load '../lib/hermetic'

setup() {
  hermetic_setup

  # Build a scratch repo with a copy of the shipped pre-push hook.
  cd "$HERMETIC_ROOT"
  git init -q -b main
  git config user.email "t@t"
  git config user.name "T"
  git commit -q --allow-empty -m "init"

  # Stage a feature branch with one commit.
  git checkout -q -b feature
  git commit -q --allow-empty -m "feat"

  # Install the shipped hook + a scripts/ dir we'll populate per scenario.
  mkdir -p "$HERMETIC_ROOT/.husky" "$HERMETIC_ROOT/scripts"
  cp "$REAL_HOOK" "$HERMETIC_ROOT/.husky/pre-push"

  # Realistic pre-push stdin: <local-ref> <local-sha> <remote-ref> <remote-sha>.
  # remote-sha is all-zeros to simulate a brand-new branch push.
  FEATURE_SHA="$(git rev-parse HEAD)"
  STDIN="refs/heads/feature $FEATURE_SHA refs/heads/feature 0000000000000000000000000000000000000000"
}

teardown() {
  hermetic_teardown
}

# Helper: write a scripts/ci-local.sh stub whose behavior is the shell body
# passed in $1. Marked executable. HUSKY_RUN_EVALS=0 disables the live-eval
# prompt so the hook doesn't hang on a controlling terminal.
_stub_ci_local() {
  cat > "$HERMETIC_ROOT/scripts/ci-local.sh" <<STUB
#!/usr/bin/env bash
$1
STUB
  chmod +x "$HERMETIC_ROOT/scripts/ci-local.sh"
}

@test "guard: refs stable + ci-local passes → hook exits 0" {
  _stub_ci_local ':'  # no-op, exit 0
  cd "$HERMETIC_ROOT"

  run env HUSKY_RUN_EVALS=0 bash -c "printf '%s\n' \"$STDIN\" | sh -e .husky/pre-push"
  [ "$status" -eq 0 ]
  # No drift diagnostic.
  ! grep -qi "ref.*drift\|ref.*changed during hook" <<<"$output"
}

@test "guard: pushing branch's ref mutated during hook → hook exits non-zero with pre/post SHAs" {
  cd "$HERMETIC_ROOT"
  ORIG="$(git rev-parse refs/heads/feature)"
  # Stub rewrites feature to a different commit while ci-local "runs".
  _stub_ci_local "cd \"$HERMETIC_ROOT\" && git commit -q --allow-empty -m evil && git update-ref refs/heads/feature HEAD"

  run env HUSKY_RUN_EVALS=0 bash -c "printf '%s\n' \"$STDIN\" | sh -e .husky/pre-push"
  [ "$status" -ne 0 ]
  # Diagnostic names the ref and both SHAs.
  [[ "$output" == *"refs/heads/feature"* ]]
  [[ "$output" == *"$ORIG"* ]]
  # Recovery hint present.
  [[ "$output" == *"git update-ref"* ]]
}

@test "guard: unrelated ref (main) mutated → hook still exits non-zero" {
  cd "$HERMETIC_ROOT"
  ORIG_MAIN="$(git rev-parse refs/heads/main)"
  _stub_ci_local "cd \"$HERMETIC_ROOT\" && git checkout -q main && git commit -q --allow-empty -m evil && git update-ref refs/heads/main HEAD && git checkout -q feature"

  run env HUSKY_RUN_EVALS=0 bash -c "printf '%s\n' \"$STDIN\" | sh -e .husky/pre-push"
  [ "$status" -ne 0 ]
  [[ "$output" == *"refs/heads/main"* ]]
  [[ "$output" == *"$ORIG_MAIN"* ]]
}

@test "guard: ref deleted during hook → hook exits non-zero" {
  cd "$HERMETIC_ROOT"
  git branch victim
  ORIG_VICTIM="$(git rev-parse refs/heads/victim)"
  _stub_ci_local "cd \"$HERMETIC_ROOT\" && git update-ref -d refs/heads/victim"

  run env HUSKY_RUN_EVALS=0 bash -c "printf '%s\n' \"$STDIN\" | sh -e .husky/pre-push"
  [ "$status" -ne 0 ]
  [[ "$output" == *"refs/heads/victim"* ]]
  [[ "$output" == *"$ORIG_VICTIM"* ]]
  [[ "$output" == *"deleted"* ]]
}

@test "guard: ref created during hook → hook exits non-zero" {
  cd "$HERMETIC_ROOT"
  _stub_ci_local "cd \"$HERMETIC_ROOT\" && git update-ref refs/heads/stray HEAD"

  run env HUSKY_RUN_EVALS=0 bash -c "printf '%s\n' \"$STDIN\" | sh -e .husky/pre-push"
  [ "$status" -ne 0 ]
  [[ "$output" == *"refs/heads/stray"* ]]
  [[ "$output" == *"created"* ]] || [[ "$output" == *"absent"* ]]
}

@test "guard: ci-local fails AND refs drifted → hook still exits non-zero and names the drift" {
  cd "$HERMETIC_ROOT"
  ORIG="$(git rev-parse refs/heads/feature)"
  _stub_ci_local "cd \"$HERMETIC_ROOT\" && git commit -q --allow-empty -m evil && git update-ref refs/heads/feature HEAD; exit 1"

  run env HUSKY_RUN_EVALS=0 bash -c "printf '%s\n' \"$STDIN\" | sh -e .husky/pre-push"
  [ "$status" -ne 0 ]
  [[ "$output" == *"refs/heads/feature"* ]]
  [[ "$output" == *"$ORIG"* ]]
}

@test "guard: ci-local fails but refs stable → hook exits non-zero from ci-local (existing behavior)" {
  cd "$HERMETIC_ROOT"
  _stub_ci_local 'exit 3'

  run env HUSKY_RUN_EVALS=0 bash -c "printf '%s\n' \"$STDIN\" | sh -e .husky/pre-push"
  [ "$status" -ne 0 ]
  # No drift diagnostic since no refs changed.
  ! grep -qi "ref.*drift\|ref.*changed during hook\|refs/heads/feature" <<<"$output"
}
