#!/usr/bin/env bats
# Slice 2 (build-worktree-inherits-caller-head): build-wave-reconcile.sh must
# carry the caller's pre-fanout WIP commits (docs/specs/<slug>.md,
# plans/<slug>.md) into the reconciled integration branch's ancestry. Today's
# script reconciles by branching `--into` fresh off `--base` (git checkout -B
# "$INTO" "$BASE"), which discards any commit made on the integration branch
# after slice branches diverged from it but before reconcile ran.
#
# Behavior under test (mirrors the plan's Slice 2 Gherkin):
#
#   Feature: build-wave-reconcile.sh carries caller WIP commits into the
#     integration branch
#
#     Scenario: WIP commit on integration branch is preserved
#       Given an integration branch with a WIP commit (spec+plan) not on
#         origin/main
#       And two slice branches created from that integration branch
#       When I run build-wave-reconcile.sh
#         --into <integration> --base origin/main
#         --test-cmd "true" <slice-1> <slice-2>
#       Then the merge succeeds
#       And "git log --format=%H <integration>" contains the WIP commit's sha
#       And the reconciled tip's tree contains the WIP commit's files
#
#     Scenario: WIP commit is preserved even when a slice adds a sibling file
#       Given the WIP commit added docs/specs/foo.md
#       And slice 1 adds an unrelated file docs/specs/bar.md
#       When reconcile runs
#       Then both files are present at the reconciled tip
#       And no manual conflict resolution was required
#
#     Scenario: same-file conflict resolution is unchanged
#       Given the WIP commit modified plans/foo.md
#       And slice 1 also modified plans/foo.md at conflicting lines
#       When reconcile runs
#       Then the pre-existing conflict-resolution behavior applies unchanged
#         (out of scope for this fix)

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
SCRIPT="$REPO_ROOT/plugins/dev-team/scripts/build_wave_reconcile.py"

load '../lib/hermetic'

setup() {
  hermetic_setup  # scrubs GIT_DIR/etc + cds into per-worker tempdir — issue #546
  T="$HERMETIC_ROOT"

  git init -q
  git config user.email "t@t.com"
  git config user.name "T"
  git checkout -q -b main

  echo "readme" >README.md
  git add README.md
  git commit -q -m "init"

  # Simulate origin/main as a separate ref pointing at the same init commit.
  git update-ref refs/remotes/origin/main main

  # integration branch, diverged from origin/main before any WIP commit.
  git checkout -q -b integration main

  # Slice branches diverge from integration BEFORE the WIP commit lands.
  git checkout -q -b slice-1 integration
  mkdir -p src
  echo "slice-1 work" >src/slice1.txt
  git add src/slice1.txt
  git commit -q -m "slice-1: add feature 1"

  git checkout -q -b slice-2 integration
  mkdir -p src
  echo "slice-2 work" >src/slice2.txt
  git add src/slice2.txt
  git commit -q -m "slice-2: add feature 2"

  # WIP commit lands on integration AFTER slice branches diverged.
  git checkout -q integration
  mkdir -p docs/specs
  echo "wip spec" >docs/specs/foo.md
  git add docs/specs/foo.md
  git commit -q -m "wip: spec+plan for foo"
  WIP_SHA="$(git rev-parse HEAD)"
  export WIP_SHA
}

teardown() {
  hermetic_teardown
}

# ---------------------------------------------------------------------------
# 2.1a — WIP commit on integration branch is preserved (base RED per the plan)
# ---------------------------------------------------------------------------

@test "2.1a: WIP commit sha survives reconcile into integration" {
  run "$SCRIPT" --into integration --base origin/main --test-cmd "true" slice-1 slice-2
  [ "$status" -eq 0 ]

  run git log --format=%H integration
  [ "$status" -eq 0 ]
  [[ "$output" == *"$WIP_SHA"* ]]
}

@test "2.1b: WIP commit's file is present at the reconciled tip" {
  run "$SCRIPT" --into integration --base origin/main --test-cmd "true" slice-1 slice-2
  [ "$status" -eq 0 ]

  [ -f docs/specs/foo.md ]
  run git show integration:docs/specs/foo.md
  [ "$status" -eq 0 ]
  [ "$output" = "wip spec" ]
}

# ---------------------------------------------------------------------------
# 2.1c — stricter probe: a second WIP commit made BETWEEN wave dispatches
# (i.e. after slice branches already exist, simulating a caller who commits
# more spec/plan work while wave 1 subagents are running) must also survive.
# This is the escalated RED the plan requires if the base scenario already
# passes on today's script.
# ---------------------------------------------------------------------------

@test "2.1c: a second WIP commit made between wave dispatches also survives" {
  git checkout -q integration
  mkdir -p plans
  echo "wip plan" >plans/foo.md
  git add plans/foo.md
  git commit -q -m "wip: second commit, made between wave dispatches"
  SECOND_WIP_SHA="$(git rev-parse HEAD)"

  run "$SCRIPT" --into integration --base origin/main --test-cmd "true" slice-1 slice-2
  [ "$status" -eq 0 ]

  run git log --format=%H integration
  [ "$status" -eq 0 ]
  [[ "$output" == *"$WIP_SHA"* ]]
  [[ "$output" == *"$SECOND_WIP_SHA"* ]]

  [ -f plans/foo.md ]
  run git show integration:plans/foo.md
  [ "$status" -eq 0 ]
  [ "$output" = "wip plan" ]
}

# ---------------------------------------------------------------------------
# 2.1d — sibling-file case: WIP file and a slice-added file both survive
# ---------------------------------------------------------------------------

@test "2.1d: WIP file and slice-added sibling file both present, no manual conflict" {
  git checkout -q slice-1
  mkdir -p docs/specs
  echo "slice-1 sibling spec" >docs/specs/bar.md
  git add docs/specs/bar.md
  git commit -q -m "slice-1: add sibling spec docs/specs/bar.md"

  run "$SCRIPT" --into integration --base origin/main --test-cmd "true" slice-1 slice-2
  [ "$status" -eq 0 ]

  run git show integration:docs/specs/foo.md
  [ "$status" -eq 0 ]
  [ "$output" = "wip spec" ]

  run git show integration:docs/specs/bar.md
  [ "$status" -eq 0 ]
  [ "$output" = "slice-1 sibling spec" ]
}

# ---------------------------------------------------------------------------
# 2.1e — same-file conflict resolution is unchanged (out of scope; regression
# guard that the existing halt-and-abort behavior still fires)
# ---------------------------------------------------------------------------

@test "2.1e: same-file conflict between WIP commit and a slice still halts the merge" {
  git checkout -q slice-1
  mkdir -p docs/specs
  echo "slice-1 conflicting edit" >docs/specs/foo.md
  git add docs/specs/foo.md
  git commit -q -m "slice-1: conflicting edit to docs/specs/foo.md"

  run "$SCRIPT" --into integration --base origin/main --test-cmd "true" slice-1 slice-2
  [ "$status" -eq 1 ]
  [[ "$output" == *"CONFLICT"* ]]
  [[ "$output" == *"docs/specs/foo.md"* ]]
}
