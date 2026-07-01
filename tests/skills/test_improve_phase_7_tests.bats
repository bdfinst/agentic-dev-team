#!/usr/bin/env bats
# Contract for /test-improve Phase 7 — executive-summary report generation.
# Issue #536, Slice 10 Step 10.2.

SKILL="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/test-improve/SKILL.md"

phase_7_section() {
  awk '
    /^### Phase 7/ {inphase=1; print; next}
    inphase && /^### / {exit}
    inphase {print}
  ' "$SKILL"
}

@test "body contains a Phase 7 section header" {
  grep -Eq '^### Phase 7' "$SKILL"
}

@test "Phase 7 names the shipped template path" {
  section=$(phase_7_section)
  echo "$section" | grep -Eq 'plugins/dev-team/skills/test-improve/templates/executive-summary\.md'
}

@test "Phase 7 names the output path shape" {
  section=$(phase_7_section)
  echo "$section" | grep -Eq 'reports/test-improve/'
  echo "$section" | grep -Eqi '<repo-slug>|<slug>'
}

@test "Phase 7 documents the interpolation rule" {
  section=$(phase_7_section)
  echo "$section" | grep -Eqi 'interpolat|placeholder|substitut'
  echo "$section" | grep -Eq 'memory/test-improve/<slug>/'
}

@test "Phase 7 documents empty-section 'Not applicable' rule" {
  section=$(phase_7_section)
  echo "$section" | grep -Eqi 'not[[:space:]]+applicable'
  echo "$section" | grep -Eqi '(do[[:space:]]+not|never|not).*(disappear|hidden|omit)'
}

@test "Phase 7 documents parent-issue-post-or-FEATURE.md link update" {
  section=$(phase_7_section)
  echo "$section" | grep -Eqi 'parent[[:space:]]+issue|FEATURE\.md'
}

@test "Phase 7 documents regeneratable-from-memory contract" {
  section=$(phase_7_section)
  echo "$section" | grep -Eqi 'regenerat|re-run.*Phase[[:space:]]+7|reproduce'
}
