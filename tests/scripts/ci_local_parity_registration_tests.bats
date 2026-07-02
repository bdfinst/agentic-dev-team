#!/usr/bin/env bats
# #574 — ci-local.sh registers a chk_parity check that runs the pytest
# harness under plugins/dev-team/tests/hooks/parity/. Backward-compatible:
# when the directory is absent (fresh clone before Phase 0 lands anywhere
# but here), the check must skip gracefully rather than error.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
CI_LOCAL="$REPO_ROOT/scripts/ci-local.sh"

@test "ci-local.sh defines chk_parity" {
  grep -qE '^chk_parity\(\)' "$CI_LOCAL"
}

@test "chk_parity is registered in the CHECKS array" {
  grep -q '::chk_parity' "$CI_LOCAL"
}

@test "chk_parity references the parity harness directory" {
  grep -q 'tests/hooks/parity' "$CI_LOCAL"
}
