#!/usr/bin/env bats

@test "claude-setup-review has Context needs: project-structure" {
  grep -q "Context needs: project-structure" \
    "$BATS_TEST_DIRNAME/../../plugins/dev-team/agents/claude-setup-review.md"
}

@test "orchestrator declares enforcement: script and an Implemented-by pointer" {
  # The orchestrator was converted to a script-enforced prose spec (PR #462):
  # it is no longer a persona-driven team agent, so instead of a "You are"
  # persona it declares `enforcement: script` and points at its implementation.
  f="$BATS_TEST_DIRNAME/../../plugins/dev-team/agents/orchestrator.md"
  grep -qE '^enforcement:[[:space:]]*script' "$f"
  grep -qE '^> \*\*Implemented by:\*\*' "$f"
}
