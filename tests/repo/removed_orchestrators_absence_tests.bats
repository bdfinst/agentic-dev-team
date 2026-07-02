#!/usr/bin/env bats
# Slice 13 — /test-modernize, /test-upgrade, test-modernization-review agent,
# and the old flow diagram are removed without aliases. Issue #536.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

@test "/test-modernize skill directory is gone" {
  [ ! -d "$REPO_ROOT/plugins/dev-team/skills/test-modernize" ]
}

@test "/test-upgrade skill directory is gone" {
  [ ! -d "$REPO_ROOT/plugins/dev-team/skills/test-upgrade" ]
}

@test "test-modernization-review agent file is gone" {
  [ ! -f "$REPO_ROOT/plugins/dev-team/agents/test-modernization-review.md" ]
}

@test "old test-modernize-flow.svg diagram is gone" {
  [ ! -f "$REPO_ROOT/plugins/dev-team/docs/diagrams/test-modernize-flow.svg" ]
}

@test "no exclusive bats fixture for /test-modernize or /test-upgrade remains" {
  # These files were removed in Slice 13.1.
  [ ! -f "$REPO_ROOT/tests/bats/stack-aware-test-modernize.bats" ]
  [ ! -f "$REPO_ROOT/tests/scripts/test_modernization_review_tests.bats" ]
  [ ! -f "$REPO_ROOT/tests/scripts/test_modernize_integration_tests.bats" ]
  [ ! -f "$REPO_ROOT/tests/skills/test_modernize_phase_4_mutation_tests.bats" ]
  [ ! -f "$REPO_ROOT/tests/skills/test_modernize_phase_review_loop_tests.bats" ]
  [ ! -f "$REPO_ROOT/tests/skills/test_upgrade_skill_tests.bats" ]
  [ ! -f "$REPO_ROOT/tests/fixtures/test-modernize-phase-1-3.snapshot.md" ]
}

@test "docs contain zero live /test-modernize references outside CHANGELOG/spec/plan" {
  # The test-improve-flow.svg diagram's <desc> element carries one historical
  # mention ("consolidates /test-modernize and /test-upgrade") for provenance —
  # allowed. All other prose docs must be clean.
  local hits
  hits=$(
    grep -rEl '/test-modernize|/test-upgrade' \
      "$REPO_ROOT/plugins/dev-team/docs/" \
      "$REPO_ROOT/plugins/dev-team/knowledge/skills-registry.md" \
      "$REPO_ROOT/plugins/dev-team/knowledge/agent-registry.md" \
      "$REPO_ROOT/README.md" 2>/dev/null \
      | grep -v 'docs/diagrams/test-improve-flow\.svg$' \
      | sort -u || true
  )
  if [ -n "$hits" ]; then
    echo "Unexpected live references to removed orchestrators:" >&2
    echo "$hits" >&2
    return 1
  fi
}

@test "worker SKILL.md files contain no live /test-modernize or /test-upgrade references" {
  local hits
  hits=$(
    grep -rEl '/test-modernize|/test-upgrade' \
      "$REPO_ROOT/plugins/dev-team/skills/coverage-baseline/SKILL.md" \
      "$REPO_ROOT/plugins/dev-team/skills/coverage-delta/SKILL.md" \
      "$REPO_ROOT/plugins/dev-team/skills/coverage-delta/references/mutation-gate.md" \
      "$REPO_ROOT/plugins/dev-team/skills/gherkin-derive/SKILL.md" \
      "$REPO_ROOT/plugins/dev-team/skills/gherkin-public/SKILL.md" \
      "$REPO_ROOT/plugins/dev-team/skills/mutation-testing/SKILL.md" \
      "$REPO_ROOT/plugins/dev-team/skills/mutation-testing/references/workflow-callers.md" \
      "$REPO_ROOT/plugins/dev-team/skills/issues-from-assessment/SKILL.md" \
      "$REPO_ROOT/plugins/dev-team/skills/test-audit-disable/SKILL.md" \
      "$REPO_ROOT/plugins/dev-team/skills/quality-targets-converge/SKILL.md" \
      2>/dev/null | sort -u || true
  )
  if [ -n "$hits" ]; then
    echo "Unexpected live references in worker SKILLs:" >&2
    echo "$hits" >&2
    return 1
  fi
}
