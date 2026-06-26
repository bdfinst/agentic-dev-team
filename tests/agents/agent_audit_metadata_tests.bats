#!/usr/bin/env bats

@test "claude-setup-review has Context needs: project-structure" {
  grep -q "Context needs: project-structure" \
    "$BATS_TEST_DIRNAME/../../plugins/dev-team/agents/claude-setup-review.md"
}

@test "test-modernization-review has Context needs: full-file" {
  grep -q "Context needs: full-file" \
    "$BATS_TEST_DIRNAME/../../plugins/dev-team/agents/test-modernization-review.md"
}

@test "orchestrator has You are persona sentence before first ## section" {
  # Extract body before first ##, check for You are
  awk '/^# /,/^## /' \
    "$BATS_TEST_DIRNAME/../../plugins/dev-team/agents/orchestrator.md" \
    | grep -q "^You are"
}
