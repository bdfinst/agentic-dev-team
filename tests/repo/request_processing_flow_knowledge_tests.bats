#!/usr/bin/env bats
# Tests for the request-processing-flow knowledge file extraction

RPF="$BATS_TEST_DIRNAME/../../plugins/dev-team/knowledge/request-processing-flow.md"

@test "request-processing-flow.md exists" {
  test -f "$RPF"
}

@test "request-processing-flow.md contains the Three-Phase Workflow section" {
  grep -q "Three-Phase Workflow" "$RPF"
}

@test "request-processing-flow.md contains the Multi-Agent Coordination section" {
  grep -q "Sub-Agents as Context Isolation" "$RPF"
}
