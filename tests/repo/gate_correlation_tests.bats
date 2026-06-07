#!/usr/bin/env bats
# #111 — per-session review-gate instrumentation + bypass↔rework correlation.
# Narrowed "process eval": does bypassing the pre-commit review gate correlate
# with more rework? The digest now carries a per-session gate block, and
# --correlate compares rework between bypass and non-bypass committing sessions.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
EXTRACT="$REPO_ROOT/scripts/session_extract.py"
PLUGIN="$REPO_ROOT/plugins/dev-team"

setup() { TMP="$(mktemp -d)"; }
teardown() { rm -rf "$TMP"; }

@test "gate: commit attempts and bypasses counted from the transcript (#111)" {
  printf '%s\n' \
    '{"type":"assistant","cwd":"/p","sessionId":"s","message":{"content":[{"type":"tool_use","name":"Bash","input":{"command":"git commit -m a"}}]}}' \
    '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Bash","input":{"command":"git commit -m b --no-verify"}}]}}' \
    '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Bash","input":{"command":"git commit -m c -n"}}]}}' \
    > "$TMP/t.jsonl"
  run python3 "$EXTRACT" --transcript "$TMP/t.jsonl" --plugin-root "$PLUGIN"
  [ "$status" -eq 0 ]
  [ "$(echo "$output" | jq -r '.gate.commit_attempts')" = "3" ]
  [ "$(echo "$output" | jq -r '.gate.commit_bypasses')" = "2" ]   # --no-verify and -n
}

@test "gate: a plain commit is not counted as a bypass (#111)" {
  printf '%s\n' \
    '{"type":"assistant","cwd":"/p","message":{"content":[{"type":"tool_use","name":"Bash","input":{"command":"git commit -m clean"}}]}}' \
    > "$TMP/t.jsonl"
  run python3 "$EXTRACT" --transcript "$TMP/t.jsonl" --plugin-root "$PLUGIN"
  [ "$(echo "$output" | jq -r '.gate.commit_attempts')" = "1" ]
  [ "$(echo "$output" | jq -r '.gate.commit_bypasses')" = "0" ]
  [ "$(echo "$output" | jq -r '.gate.bypass_rate')" = "0.0" ]
}

@test "correlate: bypass sessions with more rework are surfaced (#111)" {
  mkdir -p "$TMP/digests/box"
  cat > "$TMP/digests/box/session-digest.jsonl" <<'EOF'
{"schema":"session-sync/v1","host":"box","session_id":"b1","rework":{"failed_edits":5,"retried_bash_commands":0},"gate":{"commit_attempts":1,"commit_bypasses":1}}
{"schema":"session-sync/v1","host":"box","session_id":"b2","rework":{"failed_edits":3,"retried_bash_commands":0},"gate":{"commit_attempts":1,"commit_bypasses":1}}
{"schema":"session-sync/v1","host":"box","session_id":"g1","rework":{"failed_edits":0,"retried_bash_commands":0},"gate":{"commit_attempts":1,"commit_bypasses":0}}
{"schema":"session-sync/v1","host":"box","session_id":"g2","rework":{"failed_edits":1,"retried_bash_commands":0},"gate":{"commit_attempts":1,"commit_bypasses":0}}
EOF
  run python3 "$EXTRACT" --correlate "$TMP/digests" --plugin-root "$PLUGIN"
  [ "$status" -eq 0 ]
  [ "$(echo "$output" | jq -r '.bypass_sessions')" = "2" ]
  [ "$(echo "$output" | jq -r '.clean_sessions')" = "2" ]
  [ "$(echo "$output" | jq -r '.mean_rework_when_bypassed')" = "4.0" ]
  [ "$(echo "$output" | jq -r '.mean_rework_when_gated')" = "0.5" ]
  [[ "$(echo "$output" | jq -r '.interpretation')" == *"MORE rework"* ]]
}

@test "correlate: sessions that never committed are excluded (#111)" {
  mkdir -p "$TMP/digests/box"
  cat > "$TMP/digests/box/session-digest.jsonl" <<'EOF'
{"schema":"session-sync/v1","host":"box","session_id":"n1","rework":{"failed_edits":9},"gate":{"commit_attempts":0,"commit_bypasses":0}}
{"schema":"session-sync/v1","host":"box","session_id":"g1","rework":{"failed_edits":1},"gate":{"commit_attempts":1,"commit_bypasses":0}}
EOF
  run python3 "$EXTRACT" --correlate "$TMP/digests" --plugin-root "$PLUGIN"
  [ "$(echo "$output" | jq -r '.committing_sessions')" = "1" ]  # n1 (no commit) excluded
}

@test "slim trend + sync records carry the gate block (#111)" {
  printf '%s\n' \
    '{"type":"assistant","cwd":"/work/p","sessionId":"s","timestamp":"2026-06-07T10:00:00Z","message":{"content":[{"type":"tool_use","name":"Bash","input":{"command":"git commit -m x --no-verify"}}]}}' \
    > "$TMP/t.jsonl"
  log="$TMP/trend.jsonl"
  python3 "$EXTRACT" --transcript "$TMP/t.jsonl" --plugin-root "$PLUGIN" --append "$log" >/dev/null
  [ "$(jq -r '.gate.commit_bypasses' "$log")" = "1" ]
}
