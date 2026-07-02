#!/usr/bin/env bats
# Tests for the skills-registry knowledge file extraction

SKILLS_REG="$BATS_TEST_DIRNAME/../../plugins/dev-team/knowledge/skills-registry.md"

@test "skills-registry.md exists" {
  test -f "$SKILLS_REG"
}

@test "skills-registry.md contains the /build command with its file path" {
  grep -q "skills/build/SKILL.md" "$SKILLS_REG"
}

@test "skills-registry.md contains the /test-improve command" {
  grep -q "skills/test-improve/SKILL.md" "$SKILLS_REG"
}
