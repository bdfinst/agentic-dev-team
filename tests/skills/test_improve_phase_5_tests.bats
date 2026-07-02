#!/usr/bin/env bats
# Contract for /test-improve Phase 5 — refactor-for-testability (conditional
# on [y] from Phase 4b). Issue #536, Slice 8.

SKILL="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/test-improve/SKILL.md"

phase_5_section() {
  awk '
    /^### Phase 5/ {inphase=1; print; next}
    inphase && /^### / {exit}
    inphase {print}
  ' "$SKILL"
}

@test "body contains a Phase 5 section header" {
  grep -Eq '^### Phase 5' "$SKILL"
}

@test "Phase 5 is conditional on [y] from Phase 4b" {
  section=$(phase_5_section)
  echo "$section" | grep -Eqi '\[y\].*Phase[[:space:]]+4b|Phase[[:space:]]+4b.*\[y\]|only[[:space:]]+(when|if)|conditional'
}

@test "Phase 5 documents seam-only production-code constraint" {
  section=$(phase_5_section)
  echo "$section" | grep -Eqi 'seam[[:space:]]*(only|-only|introduction)'
}

@test "Phase 5 forbids modification or removal of existing tests" {
  section=$(phase_5_section)
  echo "$section" | grep -Eqi 'existing[[:space:]]+tests?[^.]*(may[[:space:]]+not|not).*(modif|delet|remov|edit)|(not[[:space:]]+modif|not[[:space:]]+delet|not[[:space:]]+remov).*existing[[:space:]]+tests?'
}

@test "Phase 5 documents Phase-4 precondition-check on paired Stories" {
  section=$(phase_5_section)
  echo "$section" | grep -Eqi 'precondition|Phase-4[[:space:]]+.*(closed|green)|verif.*Phase[[:space:]]+4'
}

@test "Phase 5 references the same review-loop schema as Phase 4" {
  section=$(phase_5_section)
  echo "$section" | grep -Eqi 'same[[:space:]]+.*review[[:space:]]+loop|Phase[[:space:]]+4[[:space:]]+.*review[[:space:]]+loop|review[[:space:]]+loop.*Phase[[:space:]]+4'
}

@test "Phase 5 writes phase-5-review.json with the review-loop schema" {
  section=$(phase_5_section)
  echo "$section" | grep -Eq 'memory/test-improve/<slug>/phase-5-review\.json'
}
