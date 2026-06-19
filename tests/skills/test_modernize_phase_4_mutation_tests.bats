#!/usr/bin/env bats
# Doc-shape contract for /test-modernize Phase 4 mutation orchestration
# (Slice 3 of plans/mutation-testing-every-phase.md, issue #286).
#
# Phase 4 owns the halt — Slice 2's /coverage-delta status field carries
# the signal, and Phase 4 surfaces it to the operator with three documented
# actions (strengthen / follow-up / waive) + a tool-unavailable triage.
#
# Phase 1, 2, 3 step text must NOT change in this slice. The snapshot
# fixture (captured at slice start) is the comparison ref, so this test
# is portable to shallow clones and detached HEADs — no `git merge-base
# origin/main` at test time.

SKILL="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/test-modernize/SKILL.md"
SNAPSHOT="$BATS_TEST_DIRNAME/../fixtures/test-modernize-phase-1-3.snapshot.md"

# --- Phase 4 step body extraction ------------------------------------------
# Phase 4 spans `### 4.` to the next `### 5.`.
phase4() {
  awk '/^### 4\./{f=1} /^### 5\./{f=0} f' "$SKILL"
}

# --- Phase 4 invokes /coverage-delta with --story AND --story-files --------

@test "Phase 4: invokes /coverage-delta with --story" {
  run bash -c "awk '/^### 4\./{f=1} /^### 5\./{f=0} f' '$SKILL'"
  [ "$status" -eq 0 ]
  echo "$output" | grep -q '/coverage-delta'
  echo "$output" | grep -q -- '--story\b'
}

@test "Phase 4: invokes /coverage-delta with --story-files" {
  run bash -c "awk '/^### 4\./{f=1} /^### 5\./{f=0} f' '$SKILL'"
  [ "$status" -eq 0 ]
  echo "$output" | grep -q -- '--story-files'
}

@test "Phase 4: --story-files derived from /build commit diff (not tracker CLI)" {
  # Plan AC-4 forbids tracker-CLI extraction. Assert both the positive
  # rule and the explicit prohibition appear together in the SKILL.
  run bash -c "awk '/^### 4\./{f=1} /^### 5\./{f=0} f' '$SKILL'"
  [ "$status" -eq 0 ]
  echo "$output" | grep -qiE '/build.+(commit |diff)|(commit |diff).+/build'
  echo "$output" | grep -qiE 'MUST NOT consult|must not consult|no tracker|not a tracker'
}

# --- Halt prompt template -------------------------------------------------

@test "Phase 4: documents halt prompt for net_new_survivors" {
  run bash -c "awk '/^### 4\./{f=1} /^### 5\./{f=0} f' '$SKILL'"
  [ "$status" -eq 0 ]
  echo "$output" | grep -qiE 'halt|pause.+(close|story)'
  echo "$output" | grep -q 'net_new_survivors'
}

@test "Phase 4: halt prompt names [s] strengthen action" {
  run bash -c "awk '/^### 4\./{f=1} /^### 5\./{f=0} f' '$SKILL'"
  [ "$status" -eq 0 ]
  echo "$output" | grep -qiE '\[s\].+strengthen'
}

@test "Phase 4: halt prompt names [f] follow-up action" {
  run bash -c "awk '/^### 4\./{f=1} /^### 5\./{f=0} f' '$SKILL'"
  [ "$status" -eq 0 ]
  echo "$output" | grep -qiE '\[f\].+follow.?up'
}

@test "Phase 4: halt prompt names [w] waive action" {
  run bash -c "awk '/^### 4\./{f=1} /^### 5\./{f=0} f' '$SKILL'"
  [ "$status" -eq 0 ]
  echo "$output" | grep -qiE '\[w\].+waive'
}

# --- Operator-action consequences -----------------------------------------

@test "Phase 4: waive action records reason in waivers.json" {
  run bash -c "awk '/^### 4\./{f=1} /^### 5\./{f=0} f' '$SKILL'"
  [ "$status" -eq 0 ]
  echo "$output" | grep -qE 'waivers\.json'
}

@test "Phase 4: follow-up action drafts a Phase-5 [Strengthen assertions] Story in phase-5.md" {
  run bash -c "awk '/^### 4\./{f=1} /^### 5\./{f=0} f' '$SKILL'"
  [ "$status" -eq 0 ]
  echo "$output" | grep -qE 'Strengthen assertions'
  echo "$output" | grep -qE 'phase-5\.md'
}

@test "Phase 4: strengthen action documents /continue re-entry path" {
  run bash -c "awk '/^### 4\./{f=1} /^### 5\./{f=0} f' '$SKILL'"
  [ "$status" -eq 0 ]
  echo "$output" | grep -qE '/continue|re-?enter|re-?run'
}

# --- Tool-unavailable triage ----------------------------------------------

@test "Phase 4: tool-unavailable triage names [i] install via /init-dev-team" {
  run bash -c "awk '/^### 4\./{f=1} /^### 5\./{f=0} f' '$SKILL'"
  [ "$status" -eq 0 ]
  echo "$output" | grep -qiE '\[i\].+install'
  echo "$output" | grep -qE '/init-dev-team'
}

@test "Phase 4: tool-unavailable triage names [k] skip — proceed advisory" {
  run bash -c "awk '/^### 4\./{f=1} /^### 5\./{f=0} f' '$SKILL'"
  [ "$status" -eq 0 ]
  echo "$output" | grep -qiE '\[k\].+(skip|advisory)'
}

@test "Phase 4: tool-unavailable triage names [q] quit" {
  run bash -c "awk '/^### 4\./{f=1} /^### 5\./{f=0} f' '$SKILL'"
  [ "$status" -eq 0 ]
  echo "$output" | grep -qiE '\[q\].+(quit|exit)'
}

# --- Phase 5 cross-reference ---------------------------------------------

@test "Phase 5: gains one-line cross-reference to mutation-history.json" {
  run awk '/^### 5\./{f=1} /^### 6\./{f=0} f' "$SKILL"
  [ "$status" -eq 0 ]
  echo "$output" | grep -qE 'mutation-history\.json'
}

# --- Phase 1, 2, 3 step text byte-identical to snapshot fixture ----------

@test "Phase 1-3: step text byte-identical to tests/fixtures/test-modernize-phase-1-3.snapshot.md" {
  # Re-extract Phase 1-3 from the current SKILL and diff against the
  # snapshot captured at slice start. Any drift here is a contract
  # violation — Phase 1-3 are explicitly out of scope for this slice.
  current=$(awk '/^### 1\./{f=1} /^### 4\./{f=0} f' "$SKILL")
  expected=$(cat "$SNAPSHOT")
  [ "$current" = "$expected" ]
}
