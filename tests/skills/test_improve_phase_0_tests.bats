#!/usr/bin/env bats
# Contract for the /test-improve skill Phase 0 (approach contract).
# Issue #536 — consolidation of /test-modernize + /test-upgrade.
# Slice 1 of the orchestrator plan: skeleton + Phase 0 only.
# Subsequent phases (1..7) are added in later slices.

SKILL="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/test-improve/SKILL.md"

@test "test-improve SKILL.md exists" {
  [ -f "$SKILL" ]
}

@test "frontmatter declares name test-improve" {
  fm=$(awk 'NR>1 && /^---/{exit} {print}' "$SKILL")
  echo "$fm" | grep -Eq '^name: *test-improve'
}

@test "frontmatter declares role: orchestrator" {
  fm=$(awk 'NR>1 && /^---/{exit} {print}' "$SKILL")
  echo "$fm" | grep -Eq '^role: *orchestrator'
}

@test "frontmatter declares user-invocable: true" {
  fm=$(awk 'NR>1 && /^---/{exit} {print}' "$SKILL")
  echo "$fm" | grep -Eq '^user-invocable: *true'
}

@test "argument-hint documents all five flags in the expected shape" {
  fm=$(awk 'NR>1 && /^---/{exit} {print}' "$SKILL")
  hint=$(echo "$fm" | grep -E '^argument-hint:')
  [ -n "$hint" ]
  echo "$hint" | grep -Eq '<repo-path>'
  echo "$hint" | grep -Eq -- '--parent'
  echo "$hint" | grep -Eq -- '--analyze-only'
  echo "$hint" | grep -Eq -- '--from-phase'
  echo "$hint" | grep -Eq -- '--stack'
}

@test "frontmatter declares allowed-tools" {
  fm=$(awk 'NR>1 && /^---/{exit} {print}' "$SKILL")
  echo "$fm" | grep -Eq '^allowed-tools:'
}

@test "body contains a Phase 0 section header" {
  grep -Eq '^### Phase 0' "$SKILL"
}

@test "Phase 0 prompt battery names mutation-on/off knob (default off)" {
  grep -Eqi 'mutation' "$SKILL"
  # Default off documented near the mutation prompt
  grep -Eqi 'mutation.*(default[^.]*off|off.*default)|default[^.]*off.*mutation' "$SKILL"
}

@test "Phase 0 prompt battery names BDD rubric (default none)" {
  grep -Eqi 'BDD.*rubric|rubric' "$SKILL"
  grep -Eqi 'default.*none|none.*default' "$SKILL"
}

@test "Phase 0 prompt battery names refactor mode (default no-refactor)" {
  grep -Eq 'no-refactor' "$SKILL"
  grep -Eq 'refactor-allowed' "$SKILL"
  grep -Eqi 'refactor.*(default[^.]*no-refactor|no-refactor.*default)' "$SKILL"
}

@test "Phase 0 prompt battery names quality targets knob" {
  grep -Eqi 'quality target' "$SKILL"
}

@test "Phase 0 prompt battery names sink (--parent vs local)" {
  grep -Eq -- '--parent' "$SKILL"
  grep -Eqi 'local.files|local-files|local files' "$SKILL"
}

@test "Enter accepts every default in one keystroke" {
  grep -Eqi 'Enter[^.]*accept.*default|accept.*default.*Enter|one keystroke' "$SKILL"
}

@test "Go advisory is present (go-mutesting alpha; survivor count not a gate; go test -fuzz)" {
  grep -Eqi 'go-mutesting' "$SKILL"
  grep -Eqi 'alpha' "$SKILL"
  grep -Eqi 'survivor count.*not.*gate|not a gate' "$SKILL"
  grep -Eqi 'go test -fuzz|-fuzz' "$SKILL"
}

@test "Phase 0 persistence target is memory/test-improve/<slug>/phase-0.md" {
  grep -Eq 'memory/test-improve/<slug>/phase-0\.md' "$SKILL"
}

@test "phase-0.md must exist before Phase 1 runs" {
  grep -Eqi 'phase-0\.md.*(before|prior to).*(phase 1|Phase 1)|(before|prior to).*Phase 1.*phase-0\.md' "$SKILL"
}

@test "--from-phase semantics documented (skips completed phases)" {
  grep -Eq -- '--from-phase' "$SKILL"
  grep -Eqi 'from-phase.*(skip|resume)' "$SKILL"
}

@test "--analyze-only semantics documented (exits after Phase 1)" {
  grep -Eq -- '--analyze-only' "$SKILL"
  grep -Eqi 'analyze-only.*(exit|after Phase 1)' "$SKILL"
}

@test "Phase-start banner requirement documented (Phase N/7 with settings recap)" {
  grep -Eq 'Phase N/7' "$SKILL"
  # One-line recap of active Phase-0 settings
  grep -Eqi 'mutation:.*binding:.*refactor:.*sink:' "$SKILL"
}

@test "Phase-0 answer immutability documented" {
  grep -Eqi 'immutable' "$SKILL"
  # --from-phase does not re-prompt Phase-0 inputs
  grep -Eqi 'from-phase.*not.*re-prompt|not.*re-prompt.*from-phase|delete.*phase-0\.md.*re-run' "$SKILL"
}

@test "Phase-4b prompt letter is [y/b/q] not [r]" {
  # The Phase-4b prompt uses [y] specifically (documented rationale — r is claimed elsewhere).
  grep -Eq '\[y\].*\[b\].*\[q\]|\[y/b/q\]' "$SKILL"
}
