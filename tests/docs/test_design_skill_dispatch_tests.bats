#!/usr/bin/env bats
# Skills dispatched by /test-design must be invoked via the Skill tool, not Agent.
# Regression guard for: "Agent type 'dev-team:test-design-advisor' not found"

SKILL="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/test-design/SKILL.md"

@test "test-design-advisor is dispatched with Skill tool, not Agent" {
  # Must mention Skill tool for test-design-advisor
  run grep -c "Skill(test-design-advisor" "$SKILL"
  [ "$status" -eq 0 ]
  [ "$output" -gt 0 ]
}

@test "farley-score is dispatched with Skill tool, not Agent" {
  run grep -c "Skill(farley-score" "$SKILL"
  [ "$status" -eq 0 ]
  [ "$output" -gt 0 ]
}

@test "test-design-advisor is not dispatched with bare invoke wording" {
  # 'invoke the `test-design-advisor`' without a tool call is the ambiguous form
  run grep -ci "invoke the \`test-design-advisor\`" "$SKILL"
  [ "$output" -eq 0 ]
}

@test "farley-score is not dispatched with bare invoke wording" {
  run grep -ci "invoke the \`farley-score\`" "$SKILL"
  [ "$output" -eq 0 ]
}
