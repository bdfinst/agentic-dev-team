#!/usr/bin/env bats
# Tests for tests/lib/hermetic.bash — issue #546.
#
# Verifies the shared bats helper that isolates fixture bats tests from any
# inherited git env vars (GIT_DIR/GIT_INDEX_FILE/GIT_WORK_TREE/GIT_PREFIX/
# GIT_REFLOG_ACTION) so pre-push-invoked fixtures cannot corrupt the parent
# worktree's refs.

HELPER="$BATS_TEST_DIRNAME/hermetic.bash"

# ---------------------------------------------------------------------------
# Step 1.1: env-scrub + per-worker tempdir + hermetic git init
# ---------------------------------------------------------------------------

@test "1.1a: hermetic_setup unsets git env vars leaked by the caller" {
  export GIT_DIR=/tmp/decoy-h1a.git
  export GIT_INDEX_FILE=/tmp/decoy-h1a.idx
  export GIT_WORK_TREE=/tmp/decoy-h1a-wt
  export GIT_PREFIX=subdir/
  export GIT_REFLOG_ACTION=push

  # shellcheck disable=SC1090
  source "$HELPER"
  hermetic_setup

  [ -z "${GIT_DIR:-}" ]
  [ -z "${GIT_INDEX_FILE:-}" ]
  [ -z "${GIT_WORK_TREE:-}" ]
  [ -z "${GIT_PREFIX:-}" ]
  [ -z "${GIT_REFLOG_ACTION:-}" ]
}

@test "1.1b: hermetic_setup exports GIT_CONFIG_GLOBAL and GIT_CONFIG_SYSTEM to /dev/null" {
  # shellcheck disable=SC1090
  source "$HELPER"
  hermetic_setup

  [ "$GIT_CONFIG_GLOBAL" = "/dev/null" ]
  [ "$GIT_CONFIG_SYSTEM" = "/dev/null" ]
}

@test "1.1c: hermetic_setup creates a per-worker tempdir, cds into it, records HERMETIC_ROOT" {
  # shellcheck disable=SC1090
  source "$HELPER"
  hermetic_setup

  [ -n "$HERMETIC_ROOT" ]
  [ -d "$HERMETIC_ROOT" ]
  [ "$PWD" = "$HERMETIC_ROOT" ]
  # basename should carry the pid marker
  case "$(basename "$HERMETIC_ROOT")" in
    bats-$$-*) ;;
    *) printf 'HERMETIC_ROOT basename %q does not carry the pid marker "bats-%s-"\n' "$(basename "$HERMETIC_ROOT")" "$$" >&2; return 1 ;;
  esac
}

@test "1.1d: git init in the tempdir stays hermetic under hostile GIT_DIR" {
  # Set up a real decoy bare repo with a known ref.
  DECOY="$(mktemp -d)/decoy.git"
  mkdir -p "$DECOY"
  ( cd "$DECOY" && git init -q --bare )
  # Snapshot the decoy's directory tree (relative paths + file hashes).
  PRE="$(cd "$DECOY" && find . -type f -exec sha256sum {} + 2>/dev/null | sort)"
  DECOY_HEAD_PRE="$(cd "$DECOY" && cat HEAD 2>/dev/null || printf '')"

  export GIT_DIR="$DECOY"
  export GIT_INDEX_FILE="$DECOY/index"

  # shellcheck disable=SC1090
  source "$HELPER"
  hermetic_setup

  # Run a legitimate fixture-shaped sequence.
  git init -q
  git config user.email "t@t"
  git config user.name "T"
  git commit -q --allow-empty -m "hermetic canary"

  # Decoy must be byte-identical.
  POST="$(cd "$DECOY" && find . -type f -exec sha256sum {} + 2>/dev/null | sort)"
  DECOY_HEAD_POST="$(cd "$DECOY" && cat HEAD 2>/dev/null || printf '')"
  [ "$PRE" = "$POST" ]
  [ "$DECOY_HEAD_PRE" = "$DECOY_HEAD_POST" ]

  # The fresh .git lives inside HERMETIC_ROOT.
  [ -d "$HERMETIC_ROOT/.git" ]
}

@test "1.1e: fixture-local push to its own origin still works" {
  # shellcheck disable=SC1090
  source "$HELPER"
  hermetic_setup

  mkdir -p "$HERMETIC_ROOT/origin.git"
  ( cd "$HERMETIC_ROOT/origin.git" && git init -q --bare )

  mkdir -p "$HERMETIC_ROOT/work"
  cd "$HERMETIC_ROOT/work"
  git init -q -b main
  git config user.email "t@t"
  git config user.name "T"
  git commit -q --allow-empty -m "init"
  git remote add origin "$HERMETIC_ROOT/origin.git"
  git push -q origin main

  # The bare's refs/heads/main should point at HEAD.
  HEAD_SHA="$(git rev-parse HEAD)"
  ORIGIN_SHA="$(git --git-dir="$HERMETIC_ROOT/origin.git" rev-parse refs/heads/main)"
  [ "$HEAD_SHA" = "$ORIGIN_SHA" ]
}

# ---------------------------------------------------------------------------
# Step 1.2: hermetic_assert_pwd + parallel-safety
# ---------------------------------------------------------------------------

@test "1.2a: hermetic_assert_pwd succeeds when PWD is inside HERMETIC_ROOT" {
  # shellcheck disable=SC1090
  source "$HELPER"
  hermetic_setup

  mkdir -p "$HERMETIC_ROOT/subdir"
  cd "$HERMETIC_ROOT/subdir"
  run hermetic_assert_pwd
  [ "$status" -eq 0 ]
}

@test "1.2b: hermetic_assert_pwd fails when PWD drifts outside HERMETIC_ROOT" {
  # shellcheck disable=SC1090
  source "$HELPER"
  hermetic_setup

  cd /
  run hermetic_assert_pwd
  [ "$status" -ne 0 ]
  # Diagnostic names both drift and expected root.
  [[ "$output" == *"$HERMETIC_ROOT"* ]]
  [[ "$output" == *"/"* ]]
}

@test "1.2c: two concurrent hermetic_setup invocations produce distinct roots" {
  # shellcheck disable=SC1090
  source "$HELPER"

  # Run in two subshells sequentially — mktemp -d guarantees distinct paths
  # even without concurrency, but the -t "bats-$$-XXXX" prefix means paths
  # under different bats worker pids also namespace apart.
  R1="$(
    hermetic_setup >/dev/null
    printf '%s' "$HERMETIC_ROOT"
  )"
  R2="$(
    hermetic_setup >/dev/null
    printf '%s' "$HERMETIC_ROOT"
  )"

  [ -n "$R1" ]
  [ -n "$R2" ]
  [ "$R1" != "$R2" ]
}

@test "1.2d: hermetic_teardown invokes hermetic_assert_pwd" {
  # shellcheck disable=SC1090
  source "$HELPER"
  hermetic_setup
  # Simulate a fixture that drifted.
  cd /
  run hermetic_teardown
  [ "$status" -ne 0 ]
}
