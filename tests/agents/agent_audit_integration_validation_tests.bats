#!/usr/bin/env bats
# Integration validation: all 7 agent-audit items fixed after wave 1 merges.

AGENTS="$BATS_TEST_DIRNAME/../../plugins/dev-team/agents"
HOOKS="$BATS_TEST_DIRNAME/../../plugins/dev-team/hooks"

# session-analysis: JSON output block present (fenced block after "Output JSON:")
@test "session-analysis has Output JSON: header" {
  grep -q "Output JSON:" "$AGENTS/session-analysis.md"
}

@test "session-analysis JSON block contains status pass|warn|fail|skip" {
  # Check for the fenced JSON block content, not just the header
  grep -q '"status": "pass|warn|fail|skip"' "$AGENTS/session-analysis.md"
}

@test "session-analysis has severity definitions" {
  grep -q "Severity:" "$AGENTS/session-analysis.md"
}

@test "session-analysis has Skip section" {
  grep -q "## Skip" "$AGENTS/session-analysis.md"
}

@test "session-analysis has Context needs: full-file" {
  grep -q "Context needs: full-file" "$AGENTS/session-analysis.md"
}

@test "claude-setup-review has Context needs: project-structure" {
  grep -q "Context needs: project-structure" "$AGENTS/claude-setup-review.md"
}

@test "orchestrator declares enforcement: script and an Implemented-by pointer" {
  # Script-enforced prose spec (PR #462): declares its implementation rather
  # than a "You are" persona.
  grep -qE '^enforcement:[[:space:]]*script' "$AGENTS/orchestrator.md"
  grep -qE '^> \*\*Implemented by:\*\*' "$AGENTS/orchestrator.md"
}

@test "mutation-gate does not use errexit flag" {
  ! grep -q "set -euo pipefail" "$HOOKS/mutation-gate.sh"
  grep -q "set -uo pipefail" "$HOOKS/mutation-gate.sh"
}

@test "eval-compliance-check has no bare printf variable calls" {
  ! grep -qE 'printf "\$FAILS"|printf "\$WARNINGS"' "$HOOKS/eval-compliance-check.sh"
}

@test "both hooks pass shellcheck" {
  shellcheck "$HOOKS/mutation-gate.sh"
  shellcheck "$HOOKS/eval-compliance-check.sh"
}
