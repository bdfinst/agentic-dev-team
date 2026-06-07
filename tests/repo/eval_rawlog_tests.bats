#!/usr/bin/env bats
# #180 — raw-log tier: the deterministic gate (flag only the worst sessions) and
# the privacy guard (a tier finding must stay metrics-only, no quoted payloads).
# Model-free; the live per-log pass is opt-in (run-rawlog-tier.sh).

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
RL="$REPO_ROOT/scripts/eval_rawlog.py"

setup() {
  TMP="$(mktemp -d)"; mkdir -p "$TMP/digests/box"
  cat > "$TMP/digests/box/session-digest.jsonl" <<'EOF'
{"schema":"session-sync/v1","host":"box","project":"p","session_id":"calm","rework":{"failed_edits":0},"accuracy":{"tool_calls":2,"tool_error_rate":0,"user_correction_turns":0},"gate":{"commit_bypasses":0}}
{"schema":"session-sync/v1","host":"box","project":"p","session_id":"messy","rework":{"failed_edits":8,"retried_bash_commands":4},"accuracy":{"tool_calls":10,"tool_error_rate":0.3,"user_correction_turns":2},"gate":{"commit_bypasses":1}}
{"schema":"session-sync/v1","host":"box","project":"p","session_id":"mid","rework":{"failed_edits":2},"accuracy":{"tool_calls":5,"tool_error_rate":0.1,"user_correction_turns":0},"gate":{"commit_bypasses":0}}
EOF
}
teardown() { rm -rf "$TMP"; }

@test "flag: the worst session ranks first; the gate bounds to top-N (#180)" {
  run python3 "$RL" --flag "$TMP/digests" --top 2
  [ "$status" -eq 0 ]
  [ "$(echo "$output" | jq -r '.worst_sessions | length')" = "2" ]
  [ "$(echo "$output" | jq -r '.worst_sessions[0].session_id')" = "messy" ]
  # 'calm' (lowest friction) is gated out of the top-2 — never gets the raw pass
  [ "$(echo "$output" | jq -r '[.worst_sessions[].session_id] | index("calm")')" = "null" ]
}

@test "validate: a metrics-only finding passes the privacy guard (#180)" {
  echo '[{"session_id":"messy","project":"p","friction_type":"hallucinated_citation","lens":"harness","target_artifact":"session-review","confidence":"high","count":1}]' > "$TMP/f.json"
  run python3 "$RL" --validate "$TMP/f.json"
  [ "$status" -eq 0 ]
  [ "$(echo "$output" | jq -r '.ok')" = "true" ]
  [ "$(echo "$output" | jq -r '.clean')" = "1" ]
}

@test "validate: a finding carrying a quote/payload field is rejected (#180)" {
  echo '[{"session_id":"messy","quote":"the secret is hunter2","lens":"harness"}]' > "$TMP/f.json"
  run python3 "$RL" --validate "$TMP/f.json"
  [ "$(echo "$output" | jq -r '.ok')" = "false" ]
  [[ "$(echo "$output" | jq -r '.violations[0].violations[0]')" == *"disallowed keys"* ]]
}

@test "validate: a path/code-looking value is rejected (#180)" {
  echo '[{"session_id":"messy","target_artifact":"/Users/x/secret.ts","lens":"harness"}]' > "$TMP/f.json"
  run python3 "$RL" --validate "$TMP/f.json"
  [ "$(echo "$output" | jq -r '.ok')" = "false" ]
  [[ "$(echo "$output" | jq -r '.violations[0].violations | join(" ")')" == *"path/code payload"* ]]
}

@test "validate: an unknown lens is rejected (#180)" {
  echo '[{"session_id":"messy","lens":"freeform"}]' > "$TMP/f.json"
  run python3 "$RL" --validate "$TMP/f.json"
  [ "$(echo "$output" | jq -r '.ok')" = "false" ]
}
