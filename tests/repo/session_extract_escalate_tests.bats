#!/usr/bin/env bats
# Delta C (#179): frequency -> lever escalation over the cross-machine rollup.
# rare -> hint; recurring+judgment -> instruction-rule; frequent+matchable -> hook.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
EXTRACT="$REPO_ROOT/scripts/session_extract.py"
PLUGIN="$REPO_ROOT/plugins/dev-team"

setup() {
  TMP="$(mktemp -d)"
  mkdir -p "$TMP/digests/box"
  # 2 sessions. permission_denials total 4 (rate 2.0, matchable -> hook).
  # failed_edits total 1 (rate 0.5, not matchable -> instruction-rule).
  # compaction_events total 0 across... add a rare matchable: retried_bash 1
  #   over 2 sessions = rate 0.4 (>=rare, <frequent), matchable -> instruction-rule.
  # user_correction_turns total 0 -> omitted (no count).
  cat > "$TMP/digests/box/session-digest.jsonl" <<'EOF'
{"schema":"session-sync/v1","host":"box","project":"p","session_id":"s1","tokens":{"input_tokens":1},"cost_usd":0,"rework":{"permission_denials":3,"failed_edits":1,"retried_bash_commands":1},"accuracy":{"tool_calls":1,"tool_error_rate":0,"user_correction_turns":0},"utilization":{"skills_invoked":{},"agents_invoked":{}}}
{"schema":"session-sync/v1","host":"box","project":"p","session_id":"s2","tokens":{"input_tokens":1},"cost_usd":0,"rework":{"permission_denials":1,"failed_edits":0,"retried_bash_commands":0},"accuracy":{"tool_calls":1,"tool_error_rate":0,"user_correction_turns":0},"utilization":{"skills_invoked":{},"agents_invoked":{}}}
EOF
}
teardown() { rm -rf "$TMP"; }

_esc() { python3 "$EXTRACT" --escalate "$TMP/digests" --plugin-root "$PLUGIN"; }

@test "escalate: frequent + matchable friction -> hook" {
  run _esc
  [ "$status" -eq 0 ]
  [ "$(echo "$output" | jq -r '.schema')" = "telemetry-escalation/v1" ]
  [ "$(echo "$output" | jq -r '.sessions')" = "2" ]
  # permission_denials: 4 / 2 = 2.0 rate, matchable -> hook
  [ "$(echo "$output" | jq -r '.recommendations[] | select(.signal=="permission_denials").lever')" = "hook" ]
  [ "$(echo "$output" | jq -r '.recommendations[] | select(.signal=="permission_denials").per_session_rate')" = "2.0" ]
}

@test "escalate: recurring judgment-shaped friction -> instruction-rule" {
  run _esc
  # failed_edits: 1/2 = 0.5, not matchable -> instruction-rule
  [ "$(echo "$output" | jq -r '.recommendations[] | select(.signal=="failed_edits").lever')" = "instruction-rule" ]
}

@test "escalate: matchable but below hook threshold -> instruction-rule" {
  run _esc
  # retried_bash_commands: 1/2 = 0.5 (>=rare 0.25, <frequent 1.0), matchable
  [ "$(echo "$output" | jq -r '.recommendations[] | select(.signal=="retried_bash_commands").lever')" = "instruction-rule" ]
}

@test "escalate: rare friction -> hint (threshold override)" {
  # raise rare-rate so 0.5 counts as rare
  run python3 "$EXTRACT" --escalate "$TMP/digests" --rare-rate 0.6 --plugin-root "$PLUGIN"
  [ "$status" -eq 0 ]
  [ "$(echo "$output" | jq -r '.recommendations[] | select(.signal=="failed_edits").lever')" = "hint" ]
}

@test "escalate: recommendations ranked worst-first by rate" {
  run _esc
  # permission_denials (2.0) must rank above failed_edits (0.5)
  [ "$(echo "$output" | jq -r '.recommendations[0].signal')" = "permission_denials" ]
}

@test "escalate: zero-count signals are omitted" {
  run _esc
  # user_correction_turns total 0 -> not in recommendations
  [ "$(echo "$output" | jq -r '[.recommendations[] | select(.signal=="user_correction_turns")] | length')" = "0" ]
}
