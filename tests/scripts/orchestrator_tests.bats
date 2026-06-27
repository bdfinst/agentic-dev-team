#!/usr/bin/env bats
# Slice 6 — orchestrator.py
# Covers task classification, fast-path branch, --resume flag, phase state,
# concurrent persona dispatch, and wave barrier.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
ORCH="$REPO_ROOT/scripts/orchestrator.py"

# ---------------------------------------------------------------------------
# Step 6.1 — Task classification and fast-path branch
# ---------------------------------------------------------------------------

@test "6.1a: --skip-llm with classify=trivial exits 0 and stderr shows fast path" {
  T="$(mktemp -d)"
  run python3 "$ORCH" --skip-llm --classify trivial --memory-dir "$T" <<< "do something trivial"
  rm -rf "$T"
  [ "$status" -eq 0 ]
  [[ "$output" == *"fast path"* ]] || [[ "$stderr" == *"fast path"* ]]
}

@test "6.1b: --resume with no prior state exits 1 with message" {
  T="$(mktemp -d)"
  run python3 "$ORCH" --resume --skip-llm --memory-dir "$T" <<< "some task"
  rm -rf "$T"
  [ "$status" -eq 1 ]
  [[ "$output" == *"No prior phase state found"* ]] || [[ "$stderr" == *"No prior phase state found"* ]]
}

@test "6.1c: --skip-llm with default classify (standard) exits 0" {
  T="$(mktemp -d)"
  run python3 "$ORCH" --skip-llm --memory-dir "$T" <<< "a standard task"
  rm -rf "$T"
  [ "$status" -eq 0 ]
}

# ---------------------------------------------------------------------------
# Step 6.2 — Phase state machine and --resume flag
# ---------------------------------------------------------------------------

@test "6.2a: after --skip-llm run, at least one phase state file exists in memory-dir" {
  T="$(mktemp -d)"
  python3 "$ORCH" --skip-llm --memory-dir "$T" <<< "a task" 2>/dev/null || true
  STATE_FILES=$(find "$T" -name "orchestrator-*.json" 2>/dev/null | wc -l | tr -d ' ')
  rm -rf "$T"
  [ "$STATE_FILES" -gt 0 ]
}

@test "6.2b: --resume with prior research state skips research and exits 0" {
  T="$(mktemp -d)"
  # Pre-seed research state
  echo '{"result":"prior research","files":[]}' > "$T/orchestrator-research.json"
  run python3 "$ORCH" --resume --skip-llm --memory-dir "$T" <<< "a task"
  rm -rf "$T"
  [ "$status" -eq 0 ]
}

# ---------------------------------------------------------------------------
# Step 6.3 — Concurrent persona dispatch and wave barrier
# ---------------------------------------------------------------------------

@test "6.3a: wave barrier failure prints resume hint to stderr" {
  T="$(mktemp -d)"
  run python3 "$ORCH" --skip-llm --memory-dir "$T" --fail-wave <<< "a task"
  rm -rf "$T"
  [ "$status" -eq 1 ]
  [[ "$output" == *"Resume with: python3 scripts/orchestrator.py --resume"* ]] || \
  [[ "$stderr" == *"Resume with: python3 scripts/orchestrator.py --resume"* ]]
}

@test "6.3b: --skip-llm dispatches personas and prints startup line per persona to stderr" {
  T="$(mktemp -d)"
  run python3 "$ORCH" --skip-llm --memory-dir "$T" --dispatch-personas <<< "a task"
  rm -rf "$T"
  [ "$status" -eq 0 ]
  # Should see persona dispatch lines
  [[ "$output" == *"dispatching plan-review persona"* ]] || \
  [[ "$stderr" == *"dispatching plan-review persona"* ]]
}
