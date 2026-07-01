#!/usr/bin/env bats
# Contract for /test-improve Phase 2b — derive Gherkin only when binding mode
# is not "none". Issue #536, Slice 4.

SKILL="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/test-improve/SKILL.md"

phase_2b_section() {
  awk '
    /^### Phase 2b/ {inphase=1; print; next}
    inphase && /^### / {exit}
    inphase {print}
  ' "$SKILL"
}

@test "body contains a Phase 2b section header" {
  grep -Eq '^### Phase 2b' "$SKILL"
}

@test "Phase 2b names /gherkin-derive --workflow test-improve" {
  section=$(phase_2b_section)
  echo "$section" | grep -Eq '/gherkin-derive.*--workflow[[:space:]]+test-improve'
}

@test "Phase 2b documents binding mode 'none' skip path" {
  section=$(phase_2b_section)
  echo "$section" | grep -Eqi 'none.*(skip|not[[:space:]]+invok|omit)|when[[:space:]]+.*none'
}

@test "Phase 2b documents xunit-with-annotations mode (no runner added)" {
  section=$(phase_2b_section)
  echo "$section" | grep -Eq 'xunit-with-annotations'
  echo "$section" | grep -Eqi 'no[[:space:]]+runner|without[[:space:]]+.*runner|no[[:space:]]+.*dependency'
}

@test "Phase 2b documents bdd-runner mode (native parser wired)" {
  section=$(phase_2b_section)
  echo "$section" | grep -Eq 'bdd-runner'
  echo "$section" | grep -Eqi 'parser|cucumber|specflow|reqnroll'
}

@test "Phase 2b writes .feature files under features/test-improve/" {
  section=$(phase_2b_section)
  echo "$section" | grep -Eq 'features/test-improve/'
}

@test "Phase 2b names memory/test-improve/<slug>/gherkin.md persistence" {
  section=$(phase_2b_section)
  echo "$section" | grep -Eq 'memory/test-improve/<slug>/gherkin\.md'
}

@test "Phase 2b names the human gate before Phase 3" {
  section=$(phase_2b_section)
  echo "$section" | grep -Eqi 'human[[:space:]]+gate|Phase[[:space:]]+3.*(does[[:space:]]+not|not)[[:space:]]+run|approv'
}
