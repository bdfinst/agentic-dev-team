#!/usr/bin/env bats
# Tests for root .gitignore — model routing override cache and bump log
# must be ignored so corporate config and per-user metrics never leak into
# version control. Required by AC6.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

@test ".claude/model-overrides.json is gitignored" {
  cd "$REPO_ROOT"
  run git check-ignore .claude/model-overrides.json
  [ "$status" -eq 0 ]
}

@test ".claude/metrics/model-routing.log is gitignored" {
  cd "$REPO_ROOT"
  run git check-ignore .claude/metrics/model-routing.log
  [ "$status" -eq 0 ]
}
