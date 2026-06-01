#!/usr/bin/env bats
# Spec §Agent consumer integration — Consumer usage pattern requirement.
# The orchestrator's body must explain how to resolve a knowledge anchor
# into a Read with offset/limit. This is the canonical onboarding for
# every agent that reads index entries.

ORCH="$BATS_TEST_DIRNAME/../../plugins/agentic-dev-team/agents/orchestrator.md"
ARCH_DOC="$BATS_TEST_DIRNAME/../../plugins/agentic-dev-team/docs/agent-architecture.md"

@test "orchestrator.md documents the index → offset/limit Read flow" {
  [ -f "$ORCH" ]
  # The pointer paragraph must mention all three anchors of the flow.
  grep -q "knowledge/index.json" "$ORCH"
  grep -q "offset" "$ORCH"
  grep -q "limit" "$ORCH"
}

@test "docs/agent-architecture.md cross-references the consumer usage pointer" {
  [ -f "$ARCH_DOC" ]
  grep -q "knowledge/index.json" "$ARCH_DOC"
}
