#!/usr/bin/env bats
# telemetry-sync.sh config validation (#178). Network/git paths aren't exercised
# in CI; these cover the deterministic config-resolution + --check contract that
# /session-review relies on to decide whether to prompt for a repo location.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
SYNC="$REPO_ROOT/scripts/telemetry-sync.sh"

setup() { TMP="$(mktemp -d)"; }
teardown() { rm -rf "$TMP"; }

@test "sync --check: unconfigured exits 3 with guidance" {
  run env -u DEV_TEAM_TELEMETRY_REMOTE \
    DEV_TEAM_TELEMETRY_CONFIG="$TMP/none.json" bash "$SYNC" --check
  [ "$status" -eq 3 ]
  [[ "$output" == *"No telemetry repository configured"* ]]
  [[ "$output" == *"telemetry-repo-security.md"* ]]
}

@test "sync --check: env var configures the remote (exit 0)" {
  run env DEV_TEAM_TELEMETRY_REMOTE="git@github.com:o/r.git" \
    DEV_TEAM_TELEMETRY_CONFIG="$TMP/none.json" bash "$SYNC" --check
  [ "$status" -eq 0 ]
  [[ "$output" == *"git@github.com:o/r.git"* ]]
}

@test "sync --check: config file configures the remote (exit 0)" {
  printf '%s\n' '{"remote":"git@github.com:o/r.git","host":"box1"}' > "$TMP/cfg.json"
  run env -u DEV_TEAM_TELEMETRY_REMOTE \
    DEV_TEAM_TELEMETRY_CONFIG="$TMP/cfg.json" bash "$SYNC" --check
  [ "$status" -eq 0 ]
  [[ "$output" == *"git@github.com:o/r.git"* ]]
  [[ "$output" == *"box1"* ]]
}

@test "sync --check: env var overrides the config file" {
  printf '%s\n' '{"remote":"git@github.com:from/config.git"}' > "$TMP/cfg.json"
  run env DEV_TEAM_TELEMETRY_REMOTE="git@github.com:from/env.git" \
    DEV_TEAM_TELEMETRY_CONFIG="$TMP/cfg.json" bash "$SYNC" --check
  [ "$status" -eq 0 ]
  [[ "$output" == *"from/env.git"* ]]
  [[ "$output" != *"from/config.git"* ]]
}
