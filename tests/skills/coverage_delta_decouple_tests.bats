#!/usr/bin/env bats
# Doc-shape contract for decoupling /coverage-delta from /test-modernize
# (epic #443, issue #433). The worker must run for any workflow, resolving its
# baseline / coverage-history / mutation-history paths under a --workflow
# namespace (default test-upgrade) rather than the hardcoded test-modernize one.

PLUGIN="$BATS_TEST_DIRNAME/../../plugins/dev-team"
SKILL="$PLUGIN/skills/coverage-delta/SKILL.md"
MODERNIZE="$PLUGIN/skills/test-modernize/SKILL.md"

# --- frontmatter no longer names /test-modernize as the exclusive caller ----

@test "coverage-delta: frontmatter drops 'Phase-4 worker for /test-modernize'" {
  run grep -q 'Phase-4 worker' "$SKILL"
  [ "$status" -ne 0 ]
}

@test "coverage-delta: frontmatter describes a multi-workflow worker" {
  run grep -qi 'multi-workflow' "$SKILL"
  [ "$status" -eq 0 ]
}

# --- --workflow parameter, default test-upgrade -----------------------------

@test "coverage-delta: documents the --workflow parameter" {
  run grep -q -- '--workflow' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "coverage-delta: --workflow defaults to test-upgrade" {
  run grep -Eqi 'default(ing|s)?[^.]*test-upgrade|test-upgrade[^.]*default' "$SKILL"
  [ "$status" -eq 0 ]
}

# --- memory paths are workflow-namespaced, not hardcoded --------------------

@test "coverage-delta: baseline path namespaced by <workflow>" {
  run grep -Eq 'memory/<workflow>/<slug>/baseline-coverage\.json' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "coverage-delta: coverage-history path namespaced by <workflow>" {
  run grep -Eq 'memory/<workflow>/<slug>/coverage-history\.json' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "coverage-delta: mutation-history path namespaced by <workflow>" {
  run grep -Eq 'memory/<workflow>/<slug>/mutation-history\.json' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "coverage-delta: no hardcoded memory/test-modernize path remains" {
  run grep -Eq 'memory/test-modernize/' "$SKILL"
  [ "$status" -ne 0 ]
}

# --- test-modernize call site passes --workflow test-modernize --------------

@test "test-modernize: Phase 4 invokes /coverage-delta with --workflow test-modernize" {
  run grep -E '/coverage-delta[^`]*--workflow test-modernize' "$MODERNIZE"
  [ "$status" -eq 0 ]
}
