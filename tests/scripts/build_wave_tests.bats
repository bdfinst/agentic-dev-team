#!/usr/bin/env bats
# #224 — wave-aware concurrent build: deterministic core (jobs resolution, wave
# schedule, order-independent reconcile + loud conflict halt). Model-free.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
JOBS="$REPO_ROOT/scripts/build-jobs.sh"
WAVE="$REPO_ROOT/scripts/build-wave.sh"
RECONCILE="$REPO_ROOT/scripts/build-wave-reconcile.sh"
FIX="$REPO_ROOT/tests/fixtures/plans"

# ---- build-jobs.sh ---------------------------------------------------------

# build-jobs.sh prints the effective integer on stdout and a diagnostic on stderr;
# capture stdout only (old bats `run` merges stderr, so command-substitute).

@test "jobs: effective respects the configured max (min of jobs/max/width)" {
  [ "$(DEV_TEAM_MAX_PARALLEL_BUILDS=2 "$JOBS" --jobs 5 --wave-width 4 2>/dev/null)" = "2" ]
}

@test "jobs: clamps zero/negative requested to 1" {
  [ "$(DEV_TEAM_MAX_PARALLEL_BUILDS=4 "$JOBS" --jobs 0 --wave-width 3 2>/dev/null)" = "1" ]
  [ "$(DEV_TEAM_MAX_PARALLEL_BUILDS=4 "$JOBS" --jobs -2 --wave-width 3 2>/dev/null)" = "1" ]
}

@test "jobs: non-integer requested clamps to 1" {
  [ "$(DEV_TEAM_MAX_PARALLEL_BUILDS=4 "$JOBS" --jobs abc --wave-width 3 2>/dev/null)" = "1" ]
}

@test "jobs: wave width caps concurrency" {
  [ "$(DEV_TEAM_MAX_PARALLEL_BUILDS=8 "$JOBS" --jobs 8 --wave-width 1 2>/dev/null)" = "1" ]
}

@test "jobs: default max is 2 when env unset" {
  [ "$(env -u DEV_TEAM_MAX_PARALLEL_BUILDS "$JOBS" --jobs 5 --wave-width 5 2>/dev/null)" = "2" ]
}

# ---- build-wave.sh ---------------------------------------------------------

@test "wave: emits an ordered schedule with members and reconcile order" {
  run "$WAVE" "$FIX/diamond.md"
  [ "$status" -eq 0 ]
  [ "$(echo "$output" | jq -r '.schema')" = "build-wave/v1" ]
  [ "$(echo "$output" | jq -c '[.waves[].members]')" = '[["A"],["B","C"],["D"]]' ]
  [ "$(echo "$output" | jq -c '.waves[1].reconcile_order')" = '["B","C"]' ]
}

@test "wave: refuses a schedule with a same-wave file collision" {
  run "$WAVE" "$FIX/collision.md"
  [ "$status" -ne 0 ]
  [[ "$output" == *"collision"* ]]
  [[ "$output" == *"shared.ts"* ]]
}

@test "wave: invalid plan (cycle) propagates non-zero" {
  run "$WAVE" "$FIX/cycle.md"
  [ "$status" -ne 0 ]
}

# ---- build-wave-reconcile.sh ----------------------------------------------

setup() { TMP="$(mktemp -d)"; }
teardown() { rm -rf "$TMP"; }

# Build a throwaway repo: base commit, then two slice branches off base.
_mkrepo() {  # _mkrepo <fileA> <fileB-or-same>
  git -C "$TMP" init -q
  git -C "$TMP" config user.email t@t; git -C "$TMP" config user.name t
  git -C "$TMP" config commit.gpgsign false; git -C "$TMP" config tag.gpgsign false
  echo base > "$TMP/base.txt"; git -C "$TMP" add .; git -C "$TMP" commit -qm base
  git -C "$TMP" branch slice-a; git -C "$TMP" branch slice-b
  git -C "$TMP" checkout -q slice-a; echo a > "$TMP/$1"; git -C "$TMP" add .; git -C "$TMP" commit -qm a
  git -C "$TMP" checkout -q slice-b; echo b > "$TMP/$2"; git -C "$TMP" add .; git -C "$TMP" commit -qm b
  git -C "$TMP" checkout -q main 2>/dev/null || git -C "$TMP" checkout -q master
}

@test "reconcile: disjoint-file branches merge cleanly into the integration branch" {
  _mkrepo a.txt b.txt
  run bash -c "cd '$TMP' && '$RECONCILE' --into integ --base HEAD slice-a slice-b"
  [ "$status" -eq 0 ]
  [ -f "$TMP/a.txt" ] && [ -f "$TMP/b.txt" ]
}

@test "reconcile is order-independent (same tree regardless of branch order)" {
  _mkrepo a.txt b.txt
  bash -c "cd '$TMP' && '$RECONCILE' --into i1 --base HEAD slice-a slice-b" >/dev/null
  t1="$(git -C "$TMP" rev-parse i1^{tree})"
  bash -c "cd '$TMP' && '$RECONCILE' --into i2 --base HEAD slice-b slice-a" >/dev/null
  t2="$(git -C "$TMP" rev-parse i2^{tree})"
  [ "$t1" = "$t2" ]
}

@test "reconcile: same-file conflict halts loudly, names the file, picks no side" {
  _mkrepo clash.txt clash.txt
  run bash -c "cd '$TMP' && '$RECONCILE' --into integ --base HEAD slice-a slice-b"
  [ "$status" -ne 0 ]
  [[ "$output" == *"CONFLICT"* ]]
  [[ "$output" == *"clash.txt"* ]]
  # No side chosen: the integration branch has no recorded merge conflict markers.
  ! grep -q '<<<<<<<' "$TMP/clash.txt" 2>/dev/null
}

@test "reconcile: full-suite gate failure halts before the next wave" {
  _mkrepo a.txt b.txt
  run bash -c "cd '$TMP' && '$RECONCILE' --into integ --base HEAD --test-cmd false slice-a slice-b"
  [ "$status" -ne 0 ]
  [[ "$output" == *"full-suite gate"* ]]
}
