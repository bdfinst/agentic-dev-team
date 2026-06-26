#!/usr/bin/env bats
# Tests for agents/session-analysis.md schema compliance additions.

AGENT="$BATS_TEST_DIRNAME/../../plugins/dev-team/agents/session-analysis.md"

@test "has JSON output schema with status field" {
  grep -q '"status": "pass|warn|fail|skip"' "$AGENT"
}

@test "has severity definitions covering error, warning, and suggestion" {
  grep -q "Severity:" "$AGENT"
  grep -q "error" "$AGENT"
  grep -q "warning" "$AGENT"
  grep -q "suggestion" "$AGENT"
}

@test "has a Skip section" {
  grep -q "## Skip" "$AGENT"
}
