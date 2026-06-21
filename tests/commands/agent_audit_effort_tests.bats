#!/usr/bin/env bats
# Tests for /agent-audit — it validates the effort vocabulary (effort:
# low|medium|high in frontmatter) and warns on a legacy model: tier name,
# naming the band to use. AC7.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
AUDIT="$REPO_ROOT/plugins/dev-team/skills/agent-audit/SKILL.md"
AGENTS_DIR="$REPO_ROOT/plugins/dev-team/agents"
TEMPLATES_DIR="$REPO_ROOT/plugins/dev-team/templates/agents"

@test "agent-audit validates effort: low|medium|high" {
  run grep -qE 'effort:.*low\|medium\|high' "$AUDIT"
  [ "$status" -eq 0 ]
}

@test "agent-audit warns on a legacy model: tier name" {
  # The audit names the deprecated model: tier and the band to use instead.
  grep -qi 'deprecat' "$AUDIT"
  run grep -qiE 'model:.*(haiku|sonnet|opus)' "$AUDIT"
  [ "$status" -eq 0 ]
}

@test "agent-audit no longer keys on the retired 'Model tier:' body line" {
  run grep -q 'Model tier:' "$AUDIT"
  [ "$status" -ne 0 ]
}

@test "no shipped agent body still carries a 'Model tier:' line" {
  run grep -rl 'Model tier:' "$AGENTS_DIR"
  [ "$status" -ne 0 ]
}

@test "no shipped agent template still carries a 'Model tier:' line" {
  run grep -rl 'Model tier:' "$TEMPLATES_DIR"
  [ "$status" -ne 0 ]
}
