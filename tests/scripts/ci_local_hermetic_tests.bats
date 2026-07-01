#!/usr/bin/env bats
# Tests that scripts/ci-local.sh scrubs the git env vars git exports into
# pre-push hooks (GIT_DIR / GIT_INDEX_FILE / GIT_WORK_TREE / GIT_PREFIX /
# GIT_REFLOG_ACTION) before any of its own logic runs, and that a hostile
# GIT_DIR pointing at a decoy bare repo does NOT get mutated by ci-local.sh.
#
# Uses CI_LOCAL_PROBE_ENV=1 to short-circuit ci-local: it prints the
# post-scrub set of GIT_* env vars and exits 0, so the assertion runs in
# milliseconds instead of triggering the full CI suite.
#
# Issue #546.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
CI_LOCAL="$REPO_ROOT/scripts/ci-local.sh"

load '../lib/hermetic'

setup() {
  hermetic_setup
}

teardown() {
  hermetic_teardown
}

@test "ci-local: env-scrub probe reports every targeted var as __unset__" {
  # Create the decoy first (in a clean env) so we don't fight git.
  DECOY="$HERMETIC_ROOT/decoy.git"
  mkdir -p "$DECOY" && ( cd "$DECOY" && git init -q --bare )

  # Now export a full hostile set — every var the pre-push hook could leak.
  export GIT_DIR="$DECOY"
  export GIT_INDEX_FILE="$DECOY/index"
  export GIT_WORK_TREE="$HERMETIC_ROOT/decoy-wt"
  export GIT_PREFIX="subdir/"
  export GIT_REFLOG_ACTION="push"

  # Also export a UNRELATED GIT_* variable that the probe MUST NOT leak,
  # simulating a real developer env with e.g. GIT_HTTP_EXTRAHEADER carrying
  # a bearer token. The narrowed probe should never mention it.
  export GIT_HTTP_EXTRAHEADER="Authorization: bearer SUPER_SECRET_TOKEN_XYZ"

  run env CI_LOCAL_PROBE_ENV=1 bash "$CI_LOCAL"
  [ "$status" -eq 0 ]

  # Each of the 5 scrubbed vars must report as unset.
  [[ "$output" == *"GIT_DIR=__unset__"* ]]
  [[ "$output" == *"GIT_INDEX_FILE=__unset__"* ]]
  [[ "$output" == *"GIT_WORK_TREE=__unset__"* ]]
  [[ "$output" == *"GIT_PREFIX=__unset__"* ]]
  [[ "$output" == *"GIT_REFLOG_ACTION=__unset__"* ]]

  # And critically — unrelated GIT_* secrets never appear in probe output.
  ! grep -q 'SUPER_SECRET_TOKEN_XYZ' <<<"$output"
  ! grep -q '^GIT_HTTP_EXTRAHEADER' <<<"$output"
}

@test "ci-local: hostile GIT_DIR does not mutate the decoy bare repo" {
  DECOY="$HERMETIC_ROOT/decoy.git"
  mkdir -p "$DECOY"
  ( cd "$DECOY" && git init -q --bare )

  # Snapshot before.
  PRE="$(cd "$DECOY" && find . -type f -exec sha256sum {} + 2>/dev/null | sort)"
  PRE_HEAD="$(cat "$DECOY/HEAD" 2>/dev/null || printf '')"

  export GIT_DIR="$DECOY"
  export GIT_INDEX_FILE="$DECOY/index"
  export GIT_WORK_TREE="$HERMETIC_ROOT"

  run env CI_LOCAL_PROBE_ENV=1 bash "$CI_LOCAL"
  [ "$status" -eq 0 ]

  # Snapshot after.
  POST="$(cd "$DECOY" && find . -type f -exec sha256sum {} + 2>/dev/null | sort)"
  POST_HEAD="$(cat "$DECOY/HEAD" 2>/dev/null || printf '')"

  [ "$PRE" = "$POST" ]
  [ "$PRE_HEAD" = "$POST_HEAD" ]
}
