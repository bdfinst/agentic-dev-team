#!/usr/bin/env bats
# Regression guard for #533: /test-health must pass its --path through
# to /test-design explicitly and render the scope label in its Output
# block, so a subtree audit never inherits a whole-repo score.

SKILL="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/test-health/SKILL.md"

@test "test-health SKILL documents the scoped /test-design invocation with a metavariable" {
  # Require the templated form '/test-design --path <dir>' (or a
  # ${var}-style substitution), not just the bare substring.
  run grep -Ec "/test-design --path <[^>]+>|/test-design --path \\\$\\{[^}]+\\}" "$SKILL"
  [ "$status" -eq 0 ]
  [ "$output" -gt 0 ]
}

@test "test-health SKILL documents the unscoped /test-design invocation branch" {
  # Pin the specific branch phrasing rather than any incidental /test-design
  # mention. Prior looser awk allowed lines like line 22's
  # 'come from /test-design (Farley Score + ...)' to satisfy the assertion.
  run grep -Eci "unscoped.*dispatch|dispatch .*/test-design.*(no scope flag|without --path|no --path)|/test-design.*with no scope flag" "$SKILL"
  [ "$status" -eq 0 ]
  [ "$output" -gt 0 ]
}

@test "test-health SKILL propagates the empty-scope note (no in-scope test files)" {
  run grep -c "no in-scope test files" "$SKILL"
  [ "$status" -eq 0 ]
  [ "$output" -gt 0 ]
}

@test "test-health SKILL renders a Farley Score scope label in the Output block" {
  # Slice the Output-block section before matching, so an incidental label
  # mention in Step 6 prose alone would not satisfy this assertion.
  section="$(awk '
    /^### Test-design & mutation health/ { on = 1; print; next }
    on && /^### / { on = 0 }
    on { print }
  ' "$SKILL")"
  echo "$section" | grep -Eq "\(all tests\)|\(under [^)]+\)"
}
