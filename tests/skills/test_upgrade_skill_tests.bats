#!/usr/bin/env bats
# Contract for the /test-upgrade skill (epic #443, issue #442).
# General-purpose 4-phase analyze-then-improve orchestrator.

SKILL="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/test-upgrade/SKILL.md"
AGENT_REG="$BATS_TEST_DIRNAME/../../plugins/dev-team/knowledge/agent-registry.md"
SKILLS_REG="$BATS_TEST_DIRNAME/../../plugins/dev-team/knowledge/skills-registry.md"

@test "test-upgrade SKILL.md exists" {
  [ -f "$SKILL" ]
}

@test "frontmatter declares name, user-invocable, allowed-tools" {
  fm=$(awk 'NR>1 && /^---/{exit} {print}' "$SKILL")
  echo "$fm" | grep -Eq '^name: *test-upgrade'
  echo "$fm" | grep -Eq '^user-invocable: *true'
  echo "$fm" | grep -Eq '^allowed-tools:'
}

@test "body stays under the 500-line file limit" {
  [ "$(wc -l < "$SKILL")" -lt 500 ]
}

@test "orchestrator delegates every phase, re-implements nothing" {
  grep -Eqi 'delegate' "$SKILL"
}

@test "Phase 0 detects all four languages from manifests" {
  grep -Eq 'package\.json' "$SKILL"
  grep -Eq 'pom\.xml|build\.gradle' "$SKILL"
  grep -Eq '\*?\.csproj' "$SKILL"
  grep -Eq 'go\.mod' "$SKILL"
}

@test "Phase 0 surfaces Go mutation advisory up front" {
  grep -Eqi 'go-mutesting|advisory' "$SKILL"
  grep -Eqi 'fuzz' "$SKILL"
}

@test "Phase 0 refactoring-mode choice defaults to no-refactor and persists" {
  grep -Eq 'no-refactor' "$SKILL"
  grep -Eq 'refactor-allowed' "$SKILL"
  grep -Eqi 'default' "$SKILL"
  grep -Eq 'phase-0.md' "$SKILL"
}

@test "Phase 0 presents the BDD value rubric with override" {
  grep -q 'bdd-value-guide.md' "$SKILL"
  grep -Eqi 'override' "$SKILL"
}

@test "--analyze-only exits after Phase 1 with no code changes" {
  grep -Eq -- '--analyze-only' "$SKILL"
  grep -Eqi 'exit.*Phase 1|after Phase 1|no code change' "$SKILL"
}

@test "--from-phase resumes" {
  grep -Eq -- '--from-phase' "$SKILL"
}

@test "Phase 1 delegates to /test-health" {
  grep -Eq '/test-health' "$SKILL"
}

@test "Phase 1b delegates to /gherkin-derive (skipped when binding mode none)" {
  grep -Eq '/gherkin-derive' "$SKILL"
  grep -Eqi 'none' "$SKILL"
}

@test "Phase 2 triage uses /issues-from-assessment with mode-dependent gap handling" {
  grep -Eq '/issues-from-assessment' "$SKILL"
  grep -Eq 'NO_REFACTOR' "$SKILL"
  grep -Eq 'REFACTOR_REQUIRED' "$SKILL"
  grep -Eq 'LOW_VALUE' "$SKILL"
}

@test "no-refactor: REFACTOR_REQUIRED -> backlog; refactor-allowed -> promoted" {
  grep -Eqi 'backlog' "$SKILL"
  grep -Eqi 'promot' "$SKILL"
}

@test "refactor-allowed enforces test-additions-only (no existing test modified)" {
  grep -Eqi 'test additions only|additions.only|not modif|may not.*(modif|remov)' "$SKILL"
}

@test "Phase 3 invokes /coverage-delta with --workflow test-upgrade" {
  grep -Eq '/coverage-delta[^`]*--workflow test-upgrade' "$SKILL"
}

@test "Phase 3 invokes mutation-kill --file per Story" {
  grep -Eq 'mutation-kill[^`]*--file' "$SKILL"
}

@test "Phase 3 mutation halt prompt surfaces survivor types incl. Statement advisory" {
  grep -Eqi 'survivors remain|halt' "$SKILL"
  grep -Eqi 'Statement' "$SKILL"
  grep -Eqi 'missing code path' "$SKILL"
}

@test "Phase 4 delegates to /quality-targets-converge and may run mutation-kill --all" {
  grep -Eq '/quality-targets-converge' "$SKILL"
  grep -Eq 'mutation-kill --all' "$SKILL"
}

@test "no-refactor coverage<90 surfaces REFACTOR_REQUIRED backlog + re-run instructions" {
  grep -Eqi 'coverage.*(< ?90|below 90|achieved)' "$SKILL"
  grep -Eq 'from-phase 2|refactoring allowed|refactor-allowed' "$SKILL"
}

@test "final report uses honest mutation score (timeouts separate)" {
  grep -Eqi 'honest' "$SKILL"
  grep -Eqi 'timeout' "$SKILL"
}

@test "Go mutation advisory throughout (mutation-kill logs, does not commit for Go)" {
  grep -Eqi 'advisory' "$SKILL"
  grep -Eqi 'does not commit|not commit'  "$SKILL"
}

@test "local-files mode is default; tracker requires --parent" {
  grep -Eqi 'local.files' "$SKILL"
  grep -Eq -- '--parent' "$SKILL"
}

@test "key differences from /test-modernize documented" {
  grep -Eq '/test-modernize' "$SKILL"
  grep -Eqi 'general.purpose' "$SKILL"
}

@test "registered in skills registries" {
  grep -q 'skills/test-upgrade/SKILL.md' "$SKILLS_REG"
  grep -q 'skills/test-upgrade/SKILL.md' "$AGENT_REG"
}
