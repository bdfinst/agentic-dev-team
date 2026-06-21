#!/usr/bin/env bats
# Tests for agents/orchestrator.md + CLAUDE.md routing-doc rewrite.
# Step 15 + AC2, AC14 (cross-reference), AC18 (registry pointer).

ORCH="$BATS_TEST_DIRNAME/../../plugins/dev-team/agents/orchestrator.md"
CLAUDE_MD="$BATS_TEST_DIRNAME/../../plugins/dev-team/CLAUDE.md"
ROUTING_JSON="$BATS_TEST_DIRNAME/../../plugins/dev-team/knowledge/model-routing.json"

@test "orchestrator: no static 'Model Routing Table' heading remains" {
  ! grep -qE "^##.*Model Routing Table" "$ORCH"
}

@test "orchestrator: contains a Resolution Procedure section" {
  grep -qE "^##.*Resolution Procedure" "$ORCH"
}

@test "orchestrator: Resolution Procedure names the resolver hook" {
  grep -q "hooks/agent-model-resolve.sh" "$ORCH"
}

@test "orchestrator: Resolution Procedure names the resolver helper" {
  grep -q "hooks/lib/model-resolve.sh" "$ORCH"
}

@test "orchestrator: Resolution Procedure names routing.json and the ladder" {
  grep -q "knowledge/model-routing.json" "$ORCH"
  grep -q ".claude/model-ladder.json" "$ORCH"
}

@test "orchestrator: Resolution Procedure describes effort bands" {
  grep -qE "effort:? *(band|low\|medium\|high|low, medium, high)" "$ORCH" \
    || grep -qi "effort band" "$ORCH"
}

@test "orchestrator: inline review table no longer encodes tier parentheses" {
  # The pre-rewrite table had cells like '(haiku)', '(sonnet)', '(opus)'
  # which embedded routing decisions in agent dispatch documentation. The
  # rewrite removes those parens; routing decisions live in routing.json.
  ! grep -qE "\((haiku|sonnet|opus)\)" "$ORCH"
}

@test "orchestrator: no pinned claude-(haiku|sonnet|opus)-DIGITS snapshot IDs" {
  ! grep -qE "claude-(haiku|sonnet|opus)-[0-9]" "$ORCH"
}

@test "CLAUDE.md: Model Routing section is a pointer, not a static table" {
  # The pre-rewrite block contained a markdown table with three Model rows
  # (haiku/sonnet/opus). The rewrite reduces it to one paragraph pointing
  # at the resolver hook + helper + docs.
  ! grep -qE '^\|.*\bhaiku\b.*\|' "$CLAUDE_MD"
  ! grep -qE '^\|.*\bsonnet\b.*\|' "$CLAUDE_MD"
  ! grep -qE '^\|.*\bopus\b.*\| \(opus tier\)' "$CLAUDE_MD"
  grep -q "hooks/agent-model-resolve.sh" "$CLAUDE_MD"
}

@test "CLAUDE.md: Slash Commands Registry contains a /model-routing-check row" {
  grep -qE '\| `/model-routing-check`' "$CLAUDE_MD"
}

@test "CLAUDE.md: no pinned claude-(haiku|sonnet|opus)-DIGITS snapshot IDs" {
  ! grep -qE "claude-(haiku|sonnet|opus)-[0-9]" "$CLAUDE_MD"
}
