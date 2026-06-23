#!/usr/bin/env bats
# Tests for the /artifact-lifecycle skill and harness-audit integration.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
SKILL="$REPO_ROOT/plugins/dev-team/skills/artifact-lifecycle/SKILL.md"
HARNESS_AUDIT="$REPO_ROOT/plugins/dev-team/skills/harness-audit/SKILL.md"
REGISTRY="$REPO_ROOT/plugins/dev-team/knowledge/agent-registry.md"

# ---------------------------------------------------------------------------
# Structural checks for artifact-lifecycle/SKILL.md
# ---------------------------------------------------------------------------

@test "artifact-lifecycle: SKILL.md exists" {
  [ -f "$SKILL" ]
}

@test "artifact-lifecycle: frontmatter has user-invocable: true" {
  grep -q "user-invocable: true" "$SKILL"
}

@test "artifact-lifecycle: references metrics/artifact-usage.json" {
  grep -q "artifact-usage.json" "$SKILL"
}

@test "artifact-lifecycle: documents >= 30 days stale threshold (inclusive)" {
  grep -q ">= 30" "$SKILL"
}

@test "artifact-lifecycle: documents >= 90 days archive threshold (inclusive)" {
  grep -q ">= 90" "$SKILL"
}

@test "artifact-lifecycle: references Pinned Skills exemption" {
  grep -q "Pinned Skills" "$SKILL"
}

@test "artifact-lifecycle: constrains writes to project CLAUDE.md only (not plugins/dev-team)" {
  grep -qi "plugins/dev-team" "$SKILL"
}

@test "artifact-lifecycle: describes no-data exit message" {
  grep -qi "no usage data" "$SKILL"
}

@test "artifact-lifecycle: describes all-active message" {
  grep -qi "all tracked artifacts are active" "$SKILL"
}

# ---------------------------------------------------------------------------
# harness-audit integration
# ---------------------------------------------------------------------------

@test "harness-audit: references artifact-usage.json in data-input section" {
  grep -q "artifact-usage.json" "$HARNESS_AUDIT"
}

# ---------------------------------------------------------------------------
# Registry sync
# ---------------------------------------------------------------------------

@test "registry: artifact-lifecycle is listed in agent-registry.md" {
  grep -q "artifact-lifecycle" "$REGISTRY"
}

@test "registry: artifact-lifecycle entry has a skill file path" {
  grep -q "skills/artifact-lifecycle/SKILL.md" "$REGISTRY"
}
