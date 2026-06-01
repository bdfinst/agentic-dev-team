#!/usr/bin/env bats
# AC13: ADR documenting pre-dispatch model routing decisions exists with
# the required sections and is referenced from docs/model-routing.md.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

# The ADR slot is 0004 (0001-0003 are taken). The filename is fixed for
# this test; if a future contributor renumbers, update both this test and
# the cross-reference in docs/model-routing.md.
ADR="$REPO_ROOT/docs/adr/0004-pre-dispatch-model-resolution.md"
ROUTING_DOC="$REPO_ROOT/plugins/agentic-dev-team/docs/model-routing.md"

@test "AC13: ADR file exists at docs/adr/0004-pre-dispatch-model-resolution.md" {
  [ -f "$ADR" ]
}

@test "ADR: contains the standard Status / Context / Decision / Consequences sections" {
  grep -qE "^## Status" "$ADR"
  grep -qE "^## Context" "$ADR"
  grep -qE "^## Decision" "$ADR"
  grep -qE "^## Consequences" "$ADR"
}

@test "ADR: Decision section rejects runtime model_not_available retry" {
  # Two anchors: the rejection itself and the rationale.
  grep -qi "model_not_available" "$ADR"
  grep -qi "harness owns the dispatch" "$ADR"
}

@test "ADR: Decision section records PreToolUse-hook-vs-orchestrator-instruction choice" {
  grep -qi "PreToolUse" "$ADR"
  grep -qi "orchestrator instruction" "$ADR"
}

@test "ADR: docs/model-routing.md references the ADR" {
  [ -f "$ROUTING_DOC" ]
  grep -q "0004-pre-dispatch-model-resolution" "$ROUTING_DOC"
}
