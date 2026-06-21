#!/usr/bin/env bats
# Tests for root .gitignore — the per-user model ladder and the routing bump
# log must be ignored so corporate config and per-user metrics never leak
# into version control. The retired model-overrides.json no longer needs an
# entry. Required by AC8.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

@test ".claude/model-ladder.json is gitignored" {
  cd "$REPO_ROOT"
  run git check-ignore .claude/model-ladder.json
  [ "$status" -eq 0 ]
}

@test ".claude/metrics/model-routing.log is gitignored" {
  cd "$REPO_ROOT"
  run git check-ignore .claude/metrics/model-routing.log
  [ "$status" -eq 0 ]
}
