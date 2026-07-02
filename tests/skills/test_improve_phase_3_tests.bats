#!/usr/bin/env bats
# Contract for /test-improve Phase 3 — triage via /issues-from-assessment.
# Issue #536, Slice 5.

SKILL="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/test-improve/SKILL.md"

phase_3_section() {
  awk '
    /^### Phase 3/ {inphase=1; print; next}
    inphase && /^### / {exit}
    inphase {print}
  ' "$SKILL"
}

@test "body contains a Phase 3 section header" {
  grep -Eq '^### Phase 3' "$SKILL"
}

@test "Phase 3 invokes /issues-from-assessment --workflow test-improve" {
  section=$(phase_3_section)
  echo "$section" | grep -Eq '/issues-from-assessment.*--workflow[[:space:]]+test-improve'
}

@test "Phase 3 names the NO_REFACTOR gap class" {
  section=$(phase_3_section)
  echo "$section" | grep -Eq 'NO_REFACTOR'
}

@test "Phase 3 names the REFACTOR_REQUIRED gap class" {
  section=$(phase_3_section)
  echo "$section" | grep -Eq 'REFACTOR_REQUIRED'
}

@test "Phase 3 names the LOW_VALUE gap class" {
  section=$(phase_3_section)
  echo "$section" | grep -Eq 'LOW_VALUE'
}

@test "Phase 3 documents LOW_VALUE as advisory-only" {
  section=$(phase_3_section)
  echo "$section" | grep -Eqi 'LOW_VALUE.*(advisory|no[[:space:]]+PR|no[[:space:]]+deletion|not[[:space:]]+delet)'
}

@test "Phase 3 documents REFACTOR_REQUIRED deferral to Phase 5" {
  section=$(phase_3_section)
  echo "$section" | grep -Eqi 'REFACTOR_REQUIRED.*(defer|Phase[[:space:]]+5|not[[:space:]]+written)|Phase[[:space:]]+5.*REFACTOR_REQUIRED'
}

@test "Phase 3 writes NO_REFACTOR items as Phase-4 Stories" {
  section=$(phase_3_section)
  echo "$section" | grep -Eqi 'NO_REFACTOR.*(Phase[- ]4|Stor[iy])|Stor[iy].*Phase[- ]4'
}

@test "Phase 3 names the human gate blocking Phase 4" {
  section=$(phase_3_section)
  echo "$section" | grep -Eqi 'human[[:space:]]+gate|Phase[[:space:]]+4.*(does[[:space:]]+not|not)[[:space:]]+run|approv'
}
