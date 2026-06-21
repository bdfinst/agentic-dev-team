#!/usr/bin/env bats
# Doc-shape contract for /quality-targets-converge mutation-history.json
# reuse (Slice 4 of plans/mutation-testing-every-phase.md, issue #287).
#
# Step 2 gains a "Mutation — reuse rule" sub-step that runs BEFORE the
# existing /mutation-testing invocation. Files with a non-stale, non-tool-
# unavailable history entry are reused; absent / stale / tool_unavailable
# entries are measured fresh and written back as synthetic entries.
#
# Step 4 (priority order) and Step 5 (loop body) are out of scope. The
# snapshot fixture pins their byte content — drift there is a contract
# violation. No git merge-base at test time (anti-flake for shallow clones).

SKILL="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/quality-targets-converge/SKILL.md"
SNAPSHOT="$BATS_TEST_DIRNAME/../fixtures/quality-targets-converge-steps-4-5.snapshot.md"

step2() {
  awk '/^### 2\./{f=1} /^### 3\./{f=0} f' "$SKILL"
}

# --- Reuse rule placement: BEFORE existing /mutation-testing call ----------

@test "Step 2: 'Mutation — reuse rule' heading or label appears" {
  run bash -c "awk '/^### 2\./{f=1} /^### 3\./{f=0} f' '$SKILL'"
  [ "$status" -eq 0 ]
  echo "$output" | grep -qiE 'reuse rule|mutation.+reuse'
}

@test "Step 2: reuse rule appears BEFORE the fresh /mutation-testing invocation" {
  # Line-order check: the reuse-rule bullet must come before the bullet
  # that actually invokes /mutation-testing for fresh measurement.
  # We anchor the "fresh" line on "Invoke `/mutation-testing" (with the
  # backtick) to avoid matching incidental prose references.
  reuse_line=$(awk '/^### 2\./{f=1} /^### 3\./{f=0} f' "$SKILL" | grep -inE 'reuse rule|mutation.+reuse' | head -1 | cut -d: -f1)
  mut_line=$(awk '/^### 2\./{f=1} /^### 3\./{f=0} f' "$SKILL" | grep -inE 'Invoke `/mutation-testing' | head -1 | cut -d: -f1)
  [ -n "$reuse_line" ]
  [ -n "$mut_line" ]
  [ "$reuse_line" -lt "$mut_line" ]
}

# --- Reuse rule body: mtime check + tool_unavailable exclusion ------------

@test "Step 2: reuse rule names git log --format for the mtime check" {
  run bash -c "awk '/^### 2\./{f=1} /^### 3\./{f=0} f' '$SKILL'"
  [ "$status" -eq 0 ]
  echo "$output" | grep -qE 'git log.+%cI|format=%cI'
}

@test "Step 2: reuse rule excludes tool_unavailable history entries" {
  run bash -c "awk '/^### 2\./{f=1} /^### 3\./{f=0} f' '$SKILL'"
  [ "$status" -eq 0 ]
  echo "$output" | grep -qE 'tool_unavailable'
}

@test "Step 2: documents synthetic Phase-5 write-back for freshly-measured files" {
  run bash -c "awk '/^### 2\./{f=1} /^### 3\./{f=0} f' '$SKILL'"
  [ "$status" -eq 0 ]
  echo "$output" | grep -qiE 'converge-<iteration>|synthetic.+(entry|writeback|write-back)|write.?back'
}

@test "Step 2: reuse rule names mutation-history.json as the source" {
  run bash -c "awk '/^### 2\./{f=1} /^### 3\./{f=0} f' '$SKILL'"
  [ "$status" -eq 0 ]
  echo "$output" | grep -qE 'mutation-history\.json'
}

# --- converge-<n>.json schema additions ----------------------------------

@test "Step 2: converge-<iteration>.json example names reused_from_history" {
  run bash -c "awk '/^### 2\./{f=1} /^### 3\./{f=0} f' '$SKILL'"
  [ "$status" -eq 0 ]
  echo "$output" | grep -qE 'reused_from_history'
}

@test "Step 2: converge-<iteration>.json example names measured_fresh" {
  run bash -c "awk '/^### 2\./{f=1} /^### 3\./{f=0} f' '$SKILL'"
  [ "$status" -eq 0 ]
  echo "$output" | grep -qE 'measured_fresh'
}

@test "Step 2: converge-<iteration>.json example names total_files" {
  run bash -c "awk '/^### 2\./{f=1} /^### 3\./{f=0} f' '$SKILL'"
  [ "$status" -eq 0 ]
  echo "$output" | grep -qE 'total_files'
}

# --- Backward-compat fallback --------------------------------------------

@test "Step 2: documents fallback when mutation-history.json is absent" {
  # Without this, an old /test-modernize run from before the contract is
  # silently broken. Demand a labeled paragraph.
  run bash -c "awk '/^### 2\./{f=1} /^### 3\./{f=0} f' '$SKILL'"
  [ "$status" -eq 0 ]
  echo "$output" | grep -qiE '(backward.?compat|fallback).+absent|absent.+(fallback|backward)|absent.+fall through|fall through.+absent'
}

# --- Operator visibility -------------------------------------------------

@test "Step 2 or 6: operator report names 'mutation: reused N, measured M' (cost-saving signal)" {
  # The reuse rule's only operator-visible justification is the
  # reused-vs-measured count. The Phase-5 converge report must surface it.
  run grep -iE 'reused.+measured|mutation: reused' "$SKILL"
  [ "$status" -eq 0 ]
}

# --- Step 4 and Step 5 byte-identical to snapshot ------------------------

@test "Step 4 + Step 5: step text byte-identical to snapshot fixture" {
  current=$(awk '/^### 4\./{f=1} /^### 6\./{f=0} f' "$SKILL")
  expected=$(cat "$SNAPSHOT")
  [ "$current" = "$expected" ]
}
