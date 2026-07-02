#!/usr/bin/env bats
# CI freshness gate. The shipped knowledge/index.json must match
# what a fresh build of the working tree would produce. This is the
# strict net — anything that escapes the PostToolUse hook and the
# pre-commit sibling hook is caught here.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
BUILDER="$REPO_ROOT/plugins/dev-team/hooks/lib/build_knowledge_index.py"

@test "knowledge/index.json is current with the working tree" {
  cd "$REPO_ROOT" || return 1
  run python3 "$BUILDER" --check
  [ "$status" -eq 0 ]
}
