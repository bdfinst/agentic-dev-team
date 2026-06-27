#!/usr/bin/env bats

SKILL="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/agent-audit/SKILL.md"

@test "agent-audit skill references claude_setup_review.py" {
  grep -q "scripts/claude_setup_review.py" "$SKILL"
}

@test "agent-audit skill references token_efficiency_review.py" {
  grep -q "scripts/token_efficiency_review.py" "$SKILL"
}

@test "agent-audit skill does not dispatch claude-setup-review agent" {
  ! grep -qE "(dispatch|Agent:)\s+claude-setup-review" "$SKILL"
}

@test "agent-audit skill does not dispatch token-efficiency-review agent" {
  ! grep -qE "(dispatch|Agent:)\s+token-efficiency-review" "$SKILL"
}
