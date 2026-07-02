#!/usr/bin/env bats
# Contract for /test-improve Phase 2 — baseline coverage + mutation before
# any test change. Issue #536, Slice 3.

SKILL="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/test-improve/SKILL.md"

phase_2_section() {
  awk '
    /^### Phase 2/ && !/Phase 2b/ {inphase=1; print; next}
    inphase && /^### / {exit}
    inphase {print}
  ' "$SKILL"
}

@test "body contains a Phase 2 section header" {
  grep -Eq '^### Phase 2( —|$| \()' "$SKILL"
}

@test "Phase 2 invokes /coverage-baseline with --workflow test-improve" {
  section=$(phase_2_section)
  echo "$section" | grep -Eq '/coverage-baseline.*--workflow[[:space:]]+test-improve'
}

@test "Phase 2 invokes /mutation-testing --baseline --workflow test-improve when mutation is on" {
  section=$(phase_2_section)
  echo "$section" | grep -Eq '/mutation-testing.*--baseline.*--workflow[[:space:]]+test-improve|--workflow[[:space:]]+test-improve.*--baseline'
}

@test "Phase 2 names the ordering constraint (baseline before any test file modified)" {
  section=$(phase_2_section)
  echo "$section" | grep -Eqi 'before[^.]*(any[[:space:]]+(file[[:space:]]+under[[:space:]]+)?tests?/|any[[:space:]]+test[[:space:]]+file|any[[:space:]]+test[[:space:]]+is[[:space:]]+modified|test.*(modif|edit|chang))'
}

@test "Phase 2 documents the mutation-off skip path" {
  section=$(phase_2_section)
  echo "$section" | grep -Eqi 'mutation.*off.*(skip|not[[:space:]]+(invoke|run)|omit)|when[[:space:]]+mutation[[:space:]]+is[[:space:]]+off'
}

@test "Phase 2 records baseline artifacts under memory/test-improve/<slug>/" {
  section=$(phase_2_section)
  echo "$section" | grep -Eq 'memory/test-improve/<slug>/baseline-coverage\.json'
  echo "$section" | grep -Eq 'memory/test-improve/<slug>/baseline-mutation\.json'
}

@test "Phase 2 documents the Go advisory marker on mutation baseline" {
  section=$(phase_2_section)
  echo "$section" | grep -Eqi 'go.*(advisory|advisory-only)|advisory[- ]only.*go'
}

@test "Phase 2 mutation baseline records the honest score (hard kills, timeouts separate)" {
  section=$(phase_2_section)
  echo "$section" | grep -Eqi 'hard[[:space:]]+kill'
  echo "$section" | grep -Eqi 'timeout'
}
