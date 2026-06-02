#!/usr/bin/env bats
# AC20: the knowledge index is checked into git and not gitignored.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
INDEX_PATH="plugins/dev-team/knowledge/index.json"

@test "AC20: knowledge/index.json is tracked by git" {
  cd "$REPO_ROOT"
  run git ls-files "$INDEX_PATH"
  [ "$status" -eq 0 ]
  [ "$output" = "$INDEX_PATH" ]
}

@test "AC20: knowledge/index.json is NOT gitignored" {
  cd "$REPO_ROOT"
  # git check-ignore exits 0 when ignored, 1 when NOT ignored.
  run git check-ignore "$INDEX_PATH"
  [ "$status" -ne 0 ]
}
