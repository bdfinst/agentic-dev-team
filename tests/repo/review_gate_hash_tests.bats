#!/usr/bin/env bats
# #193 — the review gate binds staged CONTENT (via review-gate-hash.sh), so
# editing a reviewed file after the gate is written re-blocks the commit. Both
# the writer (/code-review step 9) and the reader (pre-commit-review.sh) use the
# one shared helper, so they cannot diverge.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
HOOK="$REPO_ROOT/plugins/dev-team/hooks/pre-commit-review.sh"
GATEHASH="$REPO_ROOT/plugins/dev-team/hooks/lib/review-gate-hash.sh"

setup() {
  WORK="$(mktemp -d)"; cd "$WORK" || return 1
  git init -q; git config user.email t@t.dev; git config user.name tester
}
teardown() { cd / || true; rm -rf "$WORK"; }

_commit_hook() { echo '{"tool_input":{"command":"git commit -m x"}}' | bash "$HOOK"; }
_write_gate()  { bash "$GATEHASH" > .review-passed; }   # the writer side

@test "gate: the exact staged content that was reviewed commits cleanly" {
  echo v1 > a.ts; git add a.ts
  _write_gate
  run _commit_hook
  [ "$status" -eq 0 ]
  [ ! -f .review-passed ]            # consumed on success
}

@test "gate: editing a reviewed file's content re-blocks the commit (#193)" {
  echo v1 > a.ts; git add a.ts
  _write_gate                        # reviewed a.ts @ v1
  echo v2-unreviewed > a.ts; git add a.ts   # same path, new content
  run _commit_hook
  [ "$status" -eq 2 ]                # FIXED: blocked (was 0 under path-only hash)
  [[ "$output" == *"BLOCKED"* ]]
}

@test "gate: staging an extra unreviewed file re-blocks the commit (#193)" {
  echo v1 > a.ts; git add a.ts
  _write_gate
  echo new > b.ts; git add b.ts
  run _commit_hook
  [ "$status" -eq 2 ]
}

@test "gate: writer and hook compute the SAME content hash (no divergence)" {
  printf 'line1\nline2\n' > a.ts; git add a.ts
  # the helper's output (writer) must equal the hash the hook recomputes (reader)
  _write_gate
  run _commit_hook
  [ "$status" -eq 0 ]
}
