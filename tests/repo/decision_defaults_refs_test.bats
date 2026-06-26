#!/usr/bin/env bats
# Referential-integrity sensor for the approach-contract knowledge file.
# decision-defaults.md is only useful if the discovery/classification surfaces
# reference it, so this keeps the file present and wired in.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
PLUGIN="$REPO_ROOT/plugins/dev-team"
KNOWLEDGE="$PLUGIN/knowledge/decision-defaults.md"

@test "decision-defaults.md exists" {
  [ -f "$KNOWLEDGE" ]
}

@test "orchestrator references decision-defaults.md" {
  grep -q "knowledge/decision-defaults.md" "$PLUGIN/agents/orchestrator.md"
}

@test "product-manager references decision-defaults.md" {
  grep -q "knowledge/decision-defaults.md" "$PLUGIN/agents/product-manager.md"
}

@test "/plan references decision-defaults.md" {
  grep -q "knowledge/decision-defaults.md" "$PLUGIN/skills/plan/SKILL.md"
}

@test "decision-defaults.md is registered in agent-registry.md" {
  grep -q "knowledge/decision-defaults.md" "$PLUGIN/knowledge/agent-registry.md"
}

@test "context-loading-protocol has a no-task precondition (Step 0)" {
  grep -q "Step 0" "$PLUGIN/skills/context-loading-protocol/SKILL.md"
}

@test "/pr enables auto-merge by default" {
  grep -q "gh pr merge --auto" "$PLUGIN/skills/pr/SKILL.md"
}

@test "/ship skill exists and is registered" {
  [ -f "$PLUGIN/skills/ship/SKILL.md" ]
  # Skills Registry moved to knowledge/skills-registry.md; CLAUDE.md now has a pointer
  grep -q "\`/ship\`" "$PLUGIN/knowledge/skills-registry.md"
}
