#!/usr/bin/env bats
# Slice 3 / Step 3.1 — documentation gate for the worktree.baseRef=head
# settings-scope constraint from issue #553.
#
# Scenarios (from plans/build-worktree-inherits-caller-head.md Slice 3):
#
#   Scenario: orchestrator agent describes the required user action
#     Given plugins/dev-team/agents/orchestrator.md
#     When I read the Wave-Aware Build Dispatch section
#     Then it names "worktree.baseRef" and states that users must set it
#       in `.claude/settings.json` or `~/.claude/settings.json`
#
#   Scenario: request-processing-flow references the constraint
#     Given plugins/dev-team/knowledge/request-processing-flow.md
#     When I read the Implement step
#     Then it references worktree.baseRef and the settings file the user
#       is expected to edit
#
# Hermetic: this suite is grep-only against checked-in files; no git ops,
# no fs mutation. Hermetic scaffolding not required.

ROOT="${BATS_TEST_DIRNAME}/../.."

@test "orchestrator.md documents worktree.baseRef" {
  run grep -F 'worktree.baseRef' "$ROOT/plugins/dev-team/agents/orchestrator.md"
  [ "$status" -eq 0 ]
}

@test "orchestrator.md names the settings file the user must edit" {
  # Either project-level or user-level .claude/settings.json — the two
  # scopes the Slice 0 spike proved are honored.
  run bash -c "grep -E '(\\.claude/settings\\.json|~/\\.claude/settings\\.json)' '$ROOT/plugins/dev-team/agents/orchestrator.md'"
  [ "$status" -eq 0 ]
}

@test "orchestrator.md points at the spike audit trail" {
  # Non-blocking discoverability — the doc should link to the spike so a
  # reader can trace *why* only certain scopes are honored.
  run grep -F 'worktree-baseref-head-spike' "$ROOT/plugins/dev-team/agents/orchestrator.md"
  [ "$status" -eq 0 ]
}

@test "request-processing-flow.md documents worktree.baseRef" {
  run grep -F 'worktree.baseRef' "$ROOT/plugins/dev-team/knowledge/request-processing-flow.md"
  [ "$status" -eq 0 ]
}

@test "request-processing-flow.md names the settings file" {
  run bash -c "grep -E '(\\.claude/settings\\.json|~/\\.claude/settings\\.json)' '$ROOT/plugins/dev-team/knowledge/request-processing-flow.md'"
  [ "$status" -eq 0 ]
}
