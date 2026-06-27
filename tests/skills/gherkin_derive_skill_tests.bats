#!/usr/bin/env bats
# Contract for the /gherkin-derive skill (epic #443, issue #441).
# Standalone Gherkin derivation from code — no /test-modernize phase-1 map.

SKILL="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/gherkin-derive/SKILL.md"
AGENT_REG="$BATS_TEST_DIRNAME/../../plugins/dev-team/knowledge/agent-registry.md"
SKILLS_REG="$BATS_TEST_DIRNAME/../../plugins/dev-team/knowledge/skills-registry.md"

@test "gherkin-derive SKILL.md exists" {
  [ -f "$SKILL" ]
}

@test "frontmatter declares name, user-invocable, and allowed-tools" {
  fm=$(awk 'NR>1 && /^---/{exit} {print}' "$SKILL")
  echo "$fm" | grep -Eq '^name: *gherkin-derive'
  echo "$fm" | grep -Eq '^user-invocable: *true'
  echo "$fm" | grep -Eq '^allowed-tools:'
}

@test "runs standalone — does not require a test-modernize phase-1 map" {
  grep -Eqi 'standalone' "$SKILL"
  grep -Eqi 'not require|without.*phase-1|no.*phase-1|does not.*memory/test-modernize' "$SKILL"
}

@test "surface discovery tries OpenAPI -> routes -> tests -> signatures in order" {
  # Check the ordering inside the discovery step (the frontmatter summary lists
  # all four on one line, so scope to the step body).
  sect=$(awk '/Discover the public surface/{f=1} f && /^## Step 3/{exit} f' "$SKILL")
  o=$(printf '%s\n' "$sect" | grep -n -i 'OpenAPI' | head -1 | cut -d: -f1)
  r=$(printf '%s\n' "$sect" | grep -n -iE 'route' | head -1 | cut -d: -f1)
  t=$(printf '%s\n' "$sect" | grep -n -iE 'test name|describe|existing test' | head -1 | cut -d: -f1)
  s=$(printf '%s\n' "$sect" | grep -n -iE 'signature|docstring|exported function' | head -1 | cut -d: -f1)
  [ -n "$o" ] && [ -n "$r" ] && [ -n "$t" ] && [ -n "$s" ]
  [ "$o" -lt "$r" ]
  [ "$r" -lt "$t" ]
  [ "$t" -lt "$s" ]
}

@test "presents the BDD value rubric when --mode is not supplied" {
  grep -Eq -- '--mode' "$SKILL"
  grep -Eqi 'bdd-value-guide.md' "$SKILL"
  grep -Eqi 'rubric|present.*when.*not (supplied|passed)' "$SKILL"
}

@test "defines all three binding modes" {
  grep -Eq '`none`|\bnone\b' "$SKILL"
  grep -Eq 'xunit-with-annotations' "$SKILL"
  grep -Eq 'bdd-runner' "$SKILL"
}

@test "none mode exits with a recommendation and writes no files" {
  grep -Eqi 'none.*(exit|no files|no Gherkin)|exit.*recommend' "$SKILL"
}

@test "xunit-with-annotations writes .feature files only, no framework install" {
  grep -Eqi 'xunit-with-annotations' "$SKILL"
  grep -Eqi 'no.*(runner|framework|install)|not wire|do NOT wire' "$SKILL"
}

@test "bdd-runner generates pending stubs that compile and fail (not empty)" {
  grep -Eqi 'bdd-runner' "$SKILL"
  grep -Eqi 'pending' "$SKILL"
  grep -Eqi 'compile.*fail|fail.*intention|red before green|not.*empty' "$SKILL"
}

@test "labels characterization scenarios as current behavior in the .feature header" {
  grep -Eqi 'characterization' "$SKILL"
  grep -Eqi 'current behavior' "$SKILL"
}

@test "cross-references bdd-frameworks.md for per-language wiring" {
  grep -q 'bdd-frameworks.md' "$SKILL"
}

@test "writes the surface inventory under memory/test-upgrade" {
  grep -Eq 'memory/test-upgrade/.*gherkin' "$SKILL"
}

@test "registered in skills registry" {
  grep -q 'skills/gherkin-derive/SKILL.md' "$SKILLS_REG"
  grep -q 'skills/gherkin-derive/SKILL.md' "$AGENT_REG"
}
