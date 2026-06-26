#!/usr/bin/env bats
# Tests for agents/session-analysis.md schema compliance additions.

AGENT="$BATS_TEST_DIRNAME/../../plugins/dev-team/agents/session-analysis.md"

@test "has JSON output schema with status field" {
  grep -q '"status": "pass|warn|fail|skip"' "$AGENT"
}
