#!/usr/bin/env bats
# Guard: the /v1/models model probe is fully removed. Availability now comes
# from the effort ladder, not a network probe. This test fails loudly if the
# probe script, its tests, the curl shim, or any reference to them returns.
# AC6.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

# ---------------------------------------------------------------------------
# Step 4.1 — the probe files are gone
# ---------------------------------------------------------------------------

@test "model-probe.sh no longer exists" {
  [ ! -e "$REPO_ROOT/plugins/dev-team/hooks/lib/model-probe.sh" ]
}

@test "model_probe_tests.bats no longer exists" {
  [ ! -e "$REPO_ROOT/tests/hooks/model_probe_tests.bats" ]
}

@test "init_dev_team_probe_tests.bats no longer exists" {
  [ ! -e "$REPO_ROOT/tests/commands/init_dev_team_probe_tests.bats" ]
}

@test "the fake curl shim no longer exists" {
  [ ! -e "$REPO_ROOT/tests/hooks/fake-bin/curl" ]
}
