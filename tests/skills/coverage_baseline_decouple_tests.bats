#!/usr/bin/env bats
# Doc-shape contract for decoupling /coverage-baseline from /test-modernize
# (epic #443, issue #432). The worker must run for any workflow, namespacing
# its memory output under a --workflow parameter (default test-upgrade) and
# no longer requiring /test-modernize's disabled-tests.json to exist.

PLUGIN="$BATS_TEST_DIRNAME/../../plugins/dev-team"
SKILL="$PLUGIN/skills/coverage-baseline/SKILL.md"
MODERNIZE="$PLUGIN/skills/test-modernize/SKILL.md"

# --- frontmatter no longer names /test-modernize as the exclusive caller ----

@test "coverage-baseline: frontmatter drops 'Phase-3 worker for /test-modernize'" {
  run grep -q 'Phase-3 worker' "$SKILL"
  [ "$status" -ne 0 ]
}

@test "coverage-baseline: frontmatter describes a multi-workflow worker" {
  run grep -qi 'multi-workflow' "$SKILL"
  [ "$status" -eq 0 ]
}

# --- --workflow parameter, default test-upgrade -----------------------------

@test "coverage-baseline: documents the --workflow parameter" {
  run grep -q -- '--workflow' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "coverage-baseline: --workflow defaults to test-upgrade" {
  # Parse Arguments must state the default so a bare call is workflow-agnostic.
  run grep -Eqi 'default(ing|s)?[^.]*test-upgrade|test-upgrade[^.]*default' "$SKILL"
  [ "$status" -eq 0 ]
}

# --- no hard disabled-tests.json precondition -------------------------------

@test "coverage-baseline: no longer hard-requires disabled-tests.json to exist" {
  # The old Step 1 'Require memory/test-modernize/<slug>/disabled-tests.json to
  # exist ... stop' precondition must be gone so other workflows can run.
  run grep -Eq 'Require .*disabled-tests\.json.* to exist' "$SKILL"
  [ "$status" -ne 0 ]
}

# --- memory paths are workflow-namespaced, not hardcoded --------------------

@test "coverage-baseline: memory path is namespaced by <workflow>" {
  run grep -Eq 'memory/<workflow>/' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "coverage-baseline: no hardcoded memory/test-modernize path remains" {
  run grep -Eq 'memory/test-modernize/' "$SKILL"
  [ "$status" -ne 0 ]
}

# --- test-modernize call site passes --workflow test-modernize --------------

@test "test-modernize: Phase 3 invokes /coverage-baseline with --workflow test-modernize" {
  run grep -E '/coverage-baseline[^`]*--workflow test-modernize' "$MODERNIZE"
  [ "$status" -eq 0 ]
}
