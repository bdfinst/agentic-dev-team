#!/usr/bin/env bats
# Regression guard for #533: /test-health must pass its --path through
# to /test-design explicitly and render the scope label in its Output
# block, so a subtree audit never inherits a whole-repo score.

SKILL="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/test-health/SKILL.md"

@test "test-health SKILL documents the scoped /test-design invocation string" {
  # Explicit "when --path is set, dispatch /test-design --path <dir>".
  run grep -c "/test-design --path" "$SKILL"
  [ "$status" -eq 0 ]
  [ "$output" -gt 0 ]
}

@test "test-health SKILL documents the unscoped /test-design invocation" {
  # There must be at least one line that dispatches /test-design without
  # a --path token — the unscoped branch. Reject lines that mention
  # /test-design and also carry --path.
  run awk '
    BEGIN { found = 0 }
    /\/test-design/ {
      if ($0 !~ /--path/ && $0 !~ /--since/) { found = 1 }
    }
    END { exit(found ? 0 : 1) }
  ' "$SKILL"
  [ "$status" -eq 0 ]
}

@test "test-health SKILL propagates the empty-scope note (no in-scope test files)" {
  run grep -c "no in-scope test files" "$SKILL"
  [ "$status" -eq 0 ]
  [ "$output" -gt 0 ]
}

@test "test-health SKILL renders a Farley Score scope label in its Output block" {
  # Any of the three canonical labels must appear.
  run grep -Ec "\(all tests\)|\(under [^)]+\)|\(changed since [^)]+\)" "$SKILL"
  [ "$status" -eq 0 ]
  [ "$output" -gt 0 ]
}
