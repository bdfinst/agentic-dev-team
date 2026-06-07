#!/usr/bin/env bats
# #109 Phase 1 — reproduce the multiplayer collision that REMAINS even after the
# gate is content-bound (#193): two agents sharing ONE working tree share a
# single `.review-passed` file and clobber each other's gate. The resolution is
# operational, not a gate change — one git worktree per agent (see
# plugins/dev-team/docs/concurrent-use.md). The content-binding behavior itself
# is covered by review_gate_hash_tests.bats.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
HOOK="$REPO_ROOT/plugins/dev-team/hooks/pre-commit-review.sh"
GATEHASH="$REPO_ROOT/plugins/dev-team/hooks/lib/review-gate-hash.sh"

setup() {
  WORK="$(mktemp -d)"
  cd "$WORK" || return 1
  git init -q
  git config user.email t@t.dev
  git config user.name tester
}
teardown() { cd / || true; rm -rf "$WORK"; }

_commit_hook() { echo '{"tool_input":{"command":"git commit -m x"}}' | bash "$HOOK"; }
_write_gate()  { bash "$GATEHASH" > .review-passed; }

@test "baseline: a gate written for the current staged content allows the commit" {
  echo v1 > a.ts; git add a.ts
  _write_gate
  run _commit_hook
  [ "$status" -eq 0 ]
}

@test "collision: a second agent overwriting .review-passed falsely blocks the first (#109)" {
  echo v1 > a.ts; git add a.ts
  _write_gate                            # agent A passed review for its staged content
  printf 'a-different-agents-hash\n' > .review-passed  # agent B (same tree) overwrote it
  run _commit_hook                       # A commits its still-staged change
  [ "$status" -eq 2 ]                     # ...and is blocked despite having passed
  [[ "$output" == *"BLOCKED"* ]]
  # NOT fixed by content-hashing — two agents in one tree share one gate file.
  # Fix is operational: one worktree per agent (concurrent-use.md).
}
