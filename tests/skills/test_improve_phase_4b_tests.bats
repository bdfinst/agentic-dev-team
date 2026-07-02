#!/usr/bin/env bats
# Contract for /test-improve Phase 4b — refactor-decision prompt.
# Issue #536, Slice 7.

SKILL="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/test-improve/SKILL.md"

phase_4b_section() {
  awk '
    /^### Phase 4b/ {inphase=1; print; next}
    inphase && /^### / {exit}
    inphase {print}
  ' "$SKILL"
}

@test "body contains a Phase 4b section header" {
  grep -Eq '^### Phase 4b' "$SKILL"
}

@test "Phase 4b shows the REFACTOR_REQUIRED list with seam / behavior / risk columns" {
  section=$(phase_4b_section)
  echo "$section" | grep -Eqi 'seam'
  echo "$section" | grep -Eqi 'behavior'
  echo "$section" | grep -Eqi 'risk'
}

@test "Phase 4b prompt uses [y/b/q]" {
  section=$(phase_4b_section)
  echo "$section" | grep -Eq '\[y/b/q\]|\[y\].*\[b\].*\[q\]'
}

@test "Phase 4b [y] advances to Phase 5" {
  section=$(phase_4b_section)
  echo "$section" | grep -Eqi '\[y\].*Phase[[:space:]]+5|Phase[[:space:]]+5.*\[y\]'
}

@test "Phase 4b [b] writes memory/test-improve/<slug>/refactor-backlog.md and skips to Phase 6" {
  section=$(phase_4b_section)
  echo "$section" | grep -Eq 'memory/test-improve/<slug>/refactor-backlog\.md'
  echo "$section" | grep -Eqi '\[b\].*(Phase[[:space:]]+6|skip)|skip.*Phase[[:space:]]+6.*\[b\]'
}

@test "Phase 4b [q] quits before Phase 6" {
  section=$(phase_4b_section)
  echo "$section" | grep -Eqi '\[q\].*(quit|no[[:space:]]+further|stop|exit)'
}
