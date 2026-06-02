#!/usr/bin/env bats
# AC21: building the knowledge index on a clean tree must leave the
# tree clean (no untracked files, no modifications beyond the index
# file itself — which should also be unchanged when the inputs haven't
# changed). Catches temp-file or partial-write leaks.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
BUILDER="$REPO_ROOT/plugins/agentic-dev-team/hooks/lib/build-knowledge-index.sh"

@test "AC21: no temp or untracked files after a rebuild on a clean tree" {
  cd "$REPO_ROOT"
  # Only run when the tree starts clean — otherwise we'd be measuring
  # pre-existing dirt. Skip with a clear note if the repo isn't clean.
  local before
  before=$(git status --porcelain)
  if [[ -n "$before" ]]; then
    skip "tree is not clean before the test; cannot measure no-leak"
  fi
  bash "$BUILDER" >/dev/null
  local after
  after=$(git status --porcelain)
  [ -z "$after" ]
}
