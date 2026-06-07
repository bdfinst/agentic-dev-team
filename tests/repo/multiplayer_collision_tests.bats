#!/usr/bin/env bats
# #109 Phase 1 — reproduce the multiplayer collisions on the .review-passed gate.
# These are DELIBERATE failing-scenario reproductions (the assertions encode the
# CURRENT buggy behavior), so the findings in docs/spikes/multiplayer-collisions.md
# are backed by a runnable demonstration, not just prose.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
HOOK="$REPO_ROOT/plugins/dev-team/hooks/pre-commit-review.sh"

setup() {
  WORK="$(mktemp -d)"
  cd "$WORK" || return 1
  git init -q
  git config user.email t@t.dev
  git config user.name tester
}
teardown() { cd / || true; rm -rf "$WORK"; }

_commit_hook() {  # run the gate as if `git commit` was invoked
  echo '{"tool_input":{"command":"git commit -m x"}}' | bash "$HOOK"
}
_gate_hash() {    # replicate the hook's staged-paths hash
  git diff --cached --name-only | sort | shasum -a 256 2>/dev/null | cut -d' ' -f1
}

@test "baseline: a correct gate for the exact staged paths allows the commit" {
  echo v1 > a.ts; git add a.ts
  _gate_hash > .review-passed
  run _commit_hook
  [ "$status" -eq 0 ]
}

@test "collision: a second agent overwriting .review-passed falsely blocks the first (#109)" {
  echo v1 > a.ts; git add a.ts
  _gate_hash > .review-passed            # agent A passed review for {a.ts}
  printf 'a-different-set-hash\n' > .review-passed  # agent B (same tree) overwrote it
  run _commit_hook                       # A commits its still-staged {a.ts}
  [ "$status" -eq 2 ]                     # ...and is blocked despite having passed
  [[ "$output" == *"BLOCKED"* ]]
}

@test "gap: gate binds staged PATHS not CONTENT — edited content commits unreviewed (#109)" {
  echo v1 > a.ts; git add a.ts
  _gate_hash > .review-passed            # "review passed" for a.ts @ v1
  echo v2-unreviewed > a.ts; git add a.ts # same path, brand-new content
  run _commit_hook
  [ "$status" -eq 0 ]                     # allowed — the path hash still matches
  [ ! -f .review-passed ]                # gate consumed; v2 was never reviewed
}

@test "collision: shared gate is content-blind to which agent staged what (#109)" {
  # Two agents stage the SAME path set; whoever writes the gate last lets EITHER
  # commit — the gate cannot tell A's reviewed change from B's unreviewed one.
  echo a > a.ts; git add a.ts
  _gate_hash > .review-passed            # gate for {a.ts}
  echo "b unreviewed" >> a.ts; git add a.ts
  run _commit_hook
  [ "$status" -eq 0 ]                     # B's change rides A's gate
}
