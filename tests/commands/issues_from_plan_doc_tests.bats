#!/usr/bin/env bats
# #225 — /issues-from-plan must create a spec parent + slice children with
# DAG-derived dependency links, and handle a missing spec and partial failure.
# Documentation gate.

SKILL="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/issues-from-plan/SKILL.md"

@test "skill exists" {
  [ -f "$SKILL" ]
}

@test "derives dependency links from the DAG via issue-deps.sh, not file order" {
  grep -q 'issue-deps.sh' "$SKILL"
  grep -qi 'not file order' "$SKILL"
}

@test "creates a parent issue from the spec" {
  grep -qi 'parent' "$SKILL"
  grep -qi 'spec' "$SKILL"
}

@test "creates slice children linked to the parent" {
  grep -q 'Part of #' "$SKILL"
}

@test "reports a missing spec and creates no parent" {
  grep -qi 'no associated spec' "$SKILL"
  grep -qi 'create no parent' "$SKILL"
}

@test "handles partial creation failure without orphaned state" {
  grep -qi 'partial-failure' "$SKILL"
  grep -qi 'were created' "$SKILL"
}
