#!/usr/bin/env bats
# Docs + diagram + registry checks for /test-improve. Issue #536, Slice 12.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
DOCS_DIR="$REPO_ROOT/plugins/dev-team/docs"
KNOWLEDGE_DIR="$REPO_ROOT/plugins/dev-team/knowledge"

@test "test-improve-flow.svg exists and is a valid SVG" {
  local svg="$DOCS_DIR/diagrams/test-improve-flow.svg"
  [ -f "$svg" ]
  grep -Eq '<svg ' "$svg"
  grep -Eq '</svg>' "$svg"
}

@test "test-improve-flow.svg carries text labels for all 7 phases (0..7)" {
  local svg="$DOCS_DIR/diagrams/test-improve-flow.svg"
  grep -Eq 'Phase 0' "$svg"
  grep -Eq 'Phase 1' "$svg"
  grep -Eq 'Phase 2' "$svg"
  grep -Eq 'Phase 2b' "$svg"
  grep -Eq 'Phase 3' "$svg"
  grep -Eq 'Phase 4' "$svg"
  grep -Eq 'Phase 4b' "$svg"
  grep -Eq 'Phase 5' "$svg"
  grep -Eq 'Phase 6' "$svg"
  grep -Eq 'Phase 7' "$svg"
}

@test "workflows.md has a /test-improve section header" {
  grep -Eq '^## `?/test-improve' "$DOCS_DIR/workflows.md"
}

@test "workflows.md multi-phase-pipelines sentence names /test-improve alongside /ship" {
  grep -Eq '(/test-improve.*(alongside|and).*/ship)|(/ship.*(alongside|and).*/test-improve)|(/test-improve.*/ship)|(/ship.*/test-improve)' "$DOCS_DIR/workflows.md"
}

@test "agent-architecture.md embeds test-improve-flow.svg" {
  grep -Eq 'diagrams/test-improve-flow\.svg' "$DOCS_DIR/agent-architecture.md"
}

@test "skills.md has a /test-improve row" {
  grep -Eq '/test-improve' "$DOCS_DIR/skills.md"
}

@test "test-evaluation.md references /test-improve" {
  grep -Eq '/test-improve' "$DOCS_DIR/test-evaluation.md"
}

@test "team-structure.md references /test-improve" {
  grep -Eq '/test-improve' "$DOCS_DIR/team-structure.md"
}

@test "README.md references /test-improve" {
  grep -Eq '/test-improve' "$REPO_ROOT/README.md"
}

@test "skills-registry.md has a /test-improve row" {
  grep -Eq '\|[[:space:]]*`/test-improve`' "$KNOWLEDGE_DIR/skills-registry.md"
}

@test "agent-registry.md has a Test Improve row" {
  grep -Eqi 'Test[[:space:]]+Improve|test-improve' "$KNOWLEDGE_DIR/agent-registry.md"
}
