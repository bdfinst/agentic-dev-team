#!/usr/bin/env bats
# Tests for hooks/session-learning-trigger.sh — consent gate, session counter,
# threshold dispatch, session-id passthrough, and background failure handling.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
HOOK="$REPO_ROOT/plugins/dev-team/hooks/session-learning-trigger.sh"
FAKE_BIN="$BATS_TEST_DIRNAME/fake-bin"

setup() {
  D="$(mktemp -d)"
  CLAUDE_ARGS_FILE="$D/claude-args.txt"
  PYTHON3_ARGS_FILE="$D/python3-args.txt"
  export FAKE_CLAUDE_ARGS_FILE="$CLAUDE_ARGS_FILE"
  export FAKE_PYTHON3_ARGS_FILE="$PYTHON3_ARGS_FILE"
  export FAKE_CLAUDE_EXIT=0
  export FAKE_PYTHON3_EXIT=0
  # Prepend fake-bin so our shims intercept calls
  export PATH="$FAKE_BIN:$PATH"
  unset DEV_TEAM_AUTO_REVIEW 2>/dev/null || true
  unset DEV_TEAM_AUTO_REVIEW_THRESHOLD 2>/dev/null || true
}

teardown() {
  unset FAKE_CLAUDE_ARGS_FILE FAKE_PYTHON3_ARGS_FILE FAKE_CLAUDE_EXIT FAKE_PYTHON3_EXIT
  unset DEV_TEAM_AUTO_REVIEW DEV_TEAM_AUTO_REVIEW_THRESHOLD 2>/dev/null || true
  rm -rf "$D"
}

_payload() {
  local session_id="${1:-}"
  if [ -n "$session_id" ]; then
    jq -nc --arg cwd "$D" --arg sid "$session_id" \
      '{hook_event_name:"SessionStop", cwd:$cwd, session_id:$sid}'
  else
    jq -nc --arg cwd "$D" '{hook_event_name:"SessionStop", cwd:$cwd}'
  fi
}

_run_hook() {
  local payload="${1:-$(_payload)}"
  echo "$payload" | bash "$HOOK"
}

_write_state() {
  mkdir -p "$D/metrics"
  jq -nc --argjson c "$1" '{counter: $c}' > "$D/metrics/learning-loop-state.json"
}

_read_counter() {
  jq -r '.counter' "$D/metrics/learning-loop-state.json" 2>/dev/null
}

# ---------------------------------------------------------------------------
# Consent gate
# ---------------------------------------------------------------------------

@test "consent: hook exits 0 with no subprocess when DEV_TEAM_AUTO_REVIEW is unset" {
  run _run_hook
  [ "$status" -eq 0 ]
  [ ! -f "$CLAUDE_ARGS_FILE" ]
  [ ! -f "$D/metrics/learning-loop-state.json" ]
}

@test "consent: hook exits 0 when DEV_TEAM_AUTO_REVIEW=off" {
  DEV_TEAM_AUTO_REVIEW=off run _run_hook
  [ "$status" -eq 0 ]
  [ ! -f "$CLAUDE_ARGS_FILE" ]
}

# ---------------------------------------------------------------------------
# Cold-start (no state file)
# ---------------------------------------------------------------------------

@test "cold-start: creates state file with counter=1" {
  export DEV_TEAM_AUTO_REVIEW=on
  _run_hook
  [ -f "$D/metrics/learning-loop-state.json" ]
  [ "$(_read_counter)" = "1" ]
}

@test "cold-start: no background analysis dispatched" {
  export DEV_TEAM_AUTO_REVIEW=on
  _run_hook
  [ ! -f "$CLAUDE_ARGS_FILE" ]
}

# ---------------------------------------------------------------------------
# Corruption recovery
# ---------------------------------------------------------------------------

@test "corrupt state: reinitializes with counter=1" {
  export DEV_TEAM_AUTO_REVIEW=on
  mkdir -p "$D/metrics"
  echo "{{broken" > "$D/metrics/learning-loop-state.json"
  _run_hook
  [ "$(_read_counter)" = "1" ]
}

@test "corrupt state: no background analysis dispatched" {
  export DEV_TEAM_AUTO_REVIEW=on
  mkdir -p "$D/metrics"
  echo "{{broken" > "$D/metrics/learning-loop-state.json"
  _run_hook
  [ ! -f "$CLAUDE_ARGS_FILE" ]
}

@test "corrupt state: hook exits 0" {
  export DEV_TEAM_AUTO_REVIEW=on
  mkdir -p "$D/metrics"
  echo "{{broken" > "$D/metrics/learning-loop-state.json"
  run _run_hook
  [ "$status" -eq 0 ]
}

# ---------------------------------------------------------------------------
# Counter increment (below threshold)
# ---------------------------------------------------------------------------

@test "below threshold: increments counter without dispatch (3→4)" {
  export DEV_TEAM_AUTO_REVIEW=on
  _write_state 3
  _run_hook
  [ "$(_read_counter)" = "4" ]
  [ ! -f "$CLAUDE_ARGS_FILE" ]
}

@test "below threshold: increments counter without dispatch (1→2)" {
  export DEV_TEAM_AUTO_REVIEW=on
  _write_state 1
  _run_hook
  [ "$(_read_counter)" = "2" ]
}

# ---------------------------------------------------------------------------
# Threshold dispatch (default threshold=5)
# ---------------------------------------------------------------------------

@test "threshold: counter=4 + default threshold=5 → resets to 0 and dispatches" {
  export DEV_TEAM_AUTO_REVIEW=on
  _write_state 4
  _run_hook
  [ "$(_read_counter)" = "0" ]
  # Wait briefly for background process
  sleep 1
  [ -f "$PYTHON3_ARGS_FILE" ]
  grep -q "session_extract.py" "$PYTHON3_ARGS_FILE"
  grep -q -- "--since" "$PYTHON3_ARGS_FILE"
  grep -q "last" "$PYTHON3_ARGS_FILE"
}

@test "threshold: claude subprocess invoked with session-analysis argument" {
  export DEV_TEAM_AUTO_REVIEW=on
  _write_state 4
  _run_hook
  sleep 1
  [ -f "$CLAUDE_ARGS_FILE" ]
  grep -q "session-analysis" "$CLAUDE_ARGS_FILE"
}

# ---------------------------------------------------------------------------
# Custom threshold
# ---------------------------------------------------------------------------

@test "custom threshold: DEV_TEAM_AUTO_REVIEW_THRESHOLD=3 triggers at counter=2" {
  export DEV_TEAM_AUTO_REVIEW=on
  export DEV_TEAM_AUTO_REVIEW_THRESHOLD=3
  _write_state 2
  _run_hook
  [ "$(_read_counter)" = "0" ]
  sleep 1
  [ -f "$CLAUDE_ARGS_FILE" ]
}

@test "custom threshold: DEV_TEAM_AUTO_REVIEW_THRESHOLD=3 does not trigger at counter=1" {
  export DEV_TEAM_AUTO_REVIEW=on
  export DEV_TEAM_AUTO_REVIEW_THRESHOLD=3
  _write_state 1
  _run_hook
  [ "$(_read_counter)" = "2" ]
  [ ! -f "$CLAUDE_ARGS_FILE" ]
}

# ---------------------------------------------------------------------------
# Background subprocess failure: pending-review.jsonl unchanged
# ---------------------------------------------------------------------------

@test "subprocess failure: pending-review.jsonl not created on claude exit 1" {
  export DEV_TEAM_AUTO_REVIEW=on
  export FAKE_CLAUDE_EXIT=1
  _write_state 4
  _run_hook
  sleep 1
  [ ! -f "$D/metrics/pending-review.jsonl" ]
}

@test "subprocess failure: hook itself exits 0" {
  export DEV_TEAM_AUTO_REVIEW=on
  export FAKE_CLAUDE_EXIT=1
  _write_state 4
  run _run_hook
  [ "$status" -eq 0 ]
}

# ---------------------------------------------------------------------------
# session-id passthrough
# ---------------------------------------------------------------------------

@test "session-id: claude invocation includes --session-id when payload has session_id" {
  export DEV_TEAM_AUTO_REVIEW=on
  _write_state 4
  _run_hook "$(_payload "abc-123")"
  sleep 1
  [ -f "$CLAUDE_ARGS_FILE" ]
  grep -q -- "--session-id" "$CLAUDE_ARGS_FILE"
  grep -q "abc-123" "$CLAUDE_ARGS_FILE"
}

@test "session-id: claude invocation omits --session-id when payload lacks session_id" {
  export DEV_TEAM_AUTO_REVIEW=on
  _write_state 4
  _run_hook "$(_payload)"
  sleep 1
  [ -f "$CLAUDE_ARGS_FILE" ]
  ! grep -q -- "--session-id" "$CLAUDE_ARGS_FILE"
}

@test "session-id: hook exits 0 when payload lacks session_id" {
  export DEV_TEAM_AUTO_REVIEW=on
  _write_state 4
  run _run_hook "$(_payload)"
  [ "$status" -eq 0 ]
}
