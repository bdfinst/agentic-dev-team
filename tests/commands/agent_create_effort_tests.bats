#!/usr/bin/env bats
# Tests for /agent-create and /agent-add — agents are authored in the effort
# vocabulary (effort: low|medium|high), not the retired model/tier scheme.
# Invalid bands are rejected with a legacy-token mapping..

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
CREATE="$REPO_ROOT/plugins/dev-team/skills/agent-create/SKILL.md"
ADD="$REPO_ROOT/plugins/dev-team/skills/agent-add/SKILL.md"

# ---------------------------------------------------------------------------
# /agent-create authors effort bands
# ---------------------------------------------------------------------------

@test "agent-create frontmatter template declares effort, not model" {
  run grep -qE '^effort: <band>' "$CREATE"
  [ "$status" -eq 0 ]
  # The frontmatter template no longer emits a model: line.
  run grep -qE '^model: <model>' "$CREATE"
  [ "$status" -ne 0 ]
}

@test "agent-create documents the --effort flag" {
  run grep -qE '\-\-effort' "$CREATE"
  [ "$status" -eq 0 ]
}

@test "agent-create lists low/medium/high as the valid bands" {
  grep -q 'low' "$CREATE"
  grep -q 'medium' "$CREATE"
  grep -q 'high' "$CREATE"
}

@test "agent-create rejection maps a recognized legacy token to a band" {
  # The rejection guidance maps legacy tokens → bands (e.g. frontier → high).
  run grep -qiE 'frontier.*high' "$CREATE"
  [ "$status" -eq 0 ]
  run grep -qiE '(small|haiku).*low' "$CREATE"
  [ "$status" -eq 0 ]
  run grep -qiE '(mid|sonnet).*medium' "$CREATE"
  [ "$status" -eq 0 ]
}

@test "agent-create defaults review→low, team→medium" {
  run grep -qE 'effort.*\blow\b.*\bmedium\b' "$CREATE"
  [ "$status" -eq 0 ]
}

@test "agent-create body template omits the Effort line (effort is frontmatter-only)" {
  # Single source of truth: effort lives in the frontmatter template only (see
  # the frontmatter test above). The body skeleton must not restate it as an
  # `Effort: <low|medium|high>` line, and must not use the retired Model tier.
  run grep -qE 'Effort: <low\|medium\|high>' "$CREATE"
  [ "$status" -ne 0 ]
  run grep -q 'Model tier:' "$CREATE"
  [ "$status" -ne 0 ]
}

# ---------------------------------------------------------------------------
# /agent-add authors effort bands
# ---------------------------------------------------------------------------

@test "agent-add documents the --effort flag and drops --tier" {
  run grep -qE '\-\-effort low\|medium\|high' "$ADD"
  [ "$status" -eq 0 ]
  run grep -q -- '--tier' "$ADD"
  [ "$status" -ne 0 ]
}
