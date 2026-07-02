#!/usr/bin/env bats
# #224 — the /build skill + orchestrator + CLAUDE.md must document wave-aware
# concurrent build: worktree fan-out, the configurable bound, sequential fallback,
# the barrier+reconcile, the loud halt, and the cost caveat. Documentation gate.

BUILD="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/build/SKILL.md"
ORCH="$BATS_TEST_DIRNAME/../../plugins/dev-team/agents/orchestrator.md"
CLAUDEMD="$BATS_TEST_DIRNAME/../../plugins/dev-team/CLAUDE.md"

@test "build skill no longer says 'slice by slice, in order'" {
  ! grep -q 'slice by slice, in order' "$BUILD"
}

@test "build skill drives the wave schedule + jobs scripts" {
  grep -q 'build_wave.py' "$BUILD"
  grep -q 'build_jobs.py' "$BUILD"
  grep -q 'build_wave_reconcile.py' "$BUILD"
}

@test "build skill documents the configurable bound and sequential fallback" {
  grep -q 'DEV_TEAM_MAX_PARALLEL_BUILDS' "$BUILD"
  grep -qi 'sequential fallback' "$BUILD"
}

@test "build skill documents the barrier/reconcile and a loud halt" {
  grep -qi 'reconcile' "$BUILD"
  grep -qi 'no next-wave slice' "$BUILD"
}

@test "build skill surfaces the concurrency + cost caveat" {
  grep -qi 'budget faster' "$BUILD"
}

@test "build skill keeps per-slice worktree isolation" {
  grep -q 'isolation: "worktree"' "$BUILD"
}

@test "orchestrator documents wave-dispatch -> worktree -> reconcile" {
  grep -qi 'Wave-Aware Build Dispatch' "$ORCH"
  grep -q 'build_wave_reconcile.py' "$ORCH"
}

@test "CLAUDE.md documents the DEV_TEAM_MAX_PARALLEL_BUILDS env var" {
  grep -q 'DEV_TEAM_MAX_PARALLEL_BUILDS' "$CLAUDEMD"
}
