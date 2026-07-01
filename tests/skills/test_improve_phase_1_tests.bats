#!/usr/bin/env bats
# Contract for the /test-improve skill Phase 1 (analyze via /test-health).
# Issue #536 — consolidation of /test-modernize + /test-upgrade.
# Slice 2 of the orchestrator plan: Phase 1 delegates analysis to /test-health.
#
# This fixture only greps static SKILL.md text; no git or state-mutating
# operations are performed, so hermetic wiring is not required.

SKILL="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/test-improve/SKILL.md"

@test "test-improve SKILL.md exists" {
  [ -f "$SKILL" ]
}

@test "body contains a Phase 1 section header" {
  grep -Eq '^### Phase 1' "$SKILL"
}

# Extract just the Phase 1 section (from '### Phase 1' up to the next '### ' header
# or EOF) so subsequent assertions read Phase-1-owned prose, not Phase 0 leakage.
phase_1_section() {
  awk '
    /^### Phase 1/ {inphase=1; print; next}
    inphase && /^### / {exit}
    inphase {print}
  ' "$SKILL"
}

@test "Phase 1 names /test-health as the sole worker" {
  section=$(phase_1_section)
  echo "$section" | grep -Eq '/test-health'
}

@test "Phase 1 explicitly does NOT invoke /cd-test-architecture" {
  section=$(phase_1_section)
  echo "$section" | grep -Eqi '/cd-test-architecture'
  # The mention must be a non-invocation statement, not an invocation.
  echo "$section" | grep -Eqi '(not|no[t]?[[:space:]]+invoke[d]?|NOT).*(/cd-test-architecture)|(/cd-test-architecture).*(not|NOT|no[t]?[[:space:]]+invoke)'
}

@test "Phase 1 explicitly does NOT invoke /test-design" {
  section=$(phase_1_section)
  echo "$section" | grep -Eqi '/test-design'
  echo "$section" | grep -Eqi '(not|no[t]?[[:space:]]+invoke[d]?|NOT).*(/test-design)|(/test-design).*(not|NOT|no[t]?[[:space:]]+invoke)'
}

@test "Phase 1 explicitly does NOT invoke /mutation-testing separately" {
  section=$(phase_1_section)
  echo "$section" | grep -Eqi '/mutation-testing'
  echo "$section" | grep -Eqi '(not|no[t]?[[:space:]]+invoke[d]?|NOT).*(/mutation-testing)|(/mutation-testing).*(not|NOT|no[t]?[[:space:]]+invoke|separately)'
}

@test "Phase 1 mutation-off branch is documented" {
  section=$(phase_1_section)
  # Some prose acknowledging the mutation-off run path (omitted / not enabled).
  echo "$section" | grep -Eqi 'mutation.*(off|not[[:space:]]+enabled|omit)'
}

@test "Phase 1 human gate names 'the ordered improvement plan'" {
  section=$(phase_1_section)
  echo "$section" | grep -Eqi 'ordered[[:space:]]+improvement[[:space:]]+plan'
}

@test "Phase 1 gate blocks Phase 2 until approval" {
  section=$(phase_1_section)
  echo "$section" | grep -Eqi '(Phase 2|next phase).*(does not|not).*run|do[[:space:]]+not[[:space:]]+advance|human[[:space:]]+gate'
}
