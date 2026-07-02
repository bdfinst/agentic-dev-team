#!/usr/bin/env bats
# Contract for /test-improve Phase 6 — validate via /quality-targets-converge.
# Issue #536, Slice 9.

SKILL="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/test-improve/SKILL.md"

phase_6_section() {
  awk '
    /^### Phase 6/ {inphase=1; print; next}
    inphase && /^### / {exit}
    inphase {print}
  ' "$SKILL"
}

@test "body contains a Phase 6 section header" {
  grep -Eq '^### Phase 6' "$SKILL"
}

@test "Phase 6 invokes /quality-targets-converge --workflow test-improve" {
  section=$(phase_6_section)
  echo "$section" | grep -Eq '/quality-targets-converge.*--workflow[[:space:]]+test-improve'
}

@test "Phase 6 mutation target is skipped (not waived) when Phase 0 disabled mutation" {
  section=$(phase_6_section)
  echo "$section" | grep -Eqi 'mutation.*(skip|not[[:space:]]+enabled).*not[[:space:]]+waiv|not[[:space:]]+waiv.*skip'
}

@test "Phase 6 mutation target is advisory on Go" {
  section=$(phase_6_section)
  echo "$section" | grep -Eqi 'Go.*advisory|advisory.*Go'
}

@test "Phase 6 surfaces coverage-<90% re-run prompt with [y/n] shape" {
  section=$(phase_6_section)
  echo "$section" | grep -Eqi 'coverage.*90|<[[:space:]]*90'
  echo "$section" | grep -Eqi 're-run|rerun'
  echo "$section" | grep -Eq '\[y/n\]|\[y\].*\[n\]'
}

@test "Phase 6 coverage-<90% prompt lists backlogged REFACTOR_REQUIRED items" {
  section=$(phase_6_section)
  echo "$section" | grep -Eqi 'REFACTOR_REQUIRED|backlog'
}
