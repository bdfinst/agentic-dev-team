#!/usr/bin/env bats
# #182 — utilization is read from Skill/Agent tool_use (not the non-existent
# attributionSkill). #178 — `--rollup` unions all hosts' per-session sync
# records into one cross-machine view.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
EXTRACT="$REPO_ROOT/scripts/session_extract.py"
PLUGIN="$REPO_ROOT/plugins/dev-team"

setup() { TMP="$(mktemp -d)"; }
teardown() { rm -rf "$TMP"; }

# ---- #182: utilization from tool_use ------------------------------------
@test "utilization: skills/agents counted from Skill/Agent tool_use (#182)" {
  cat > "$TMP/t.jsonl" <<'EOF'
{"type":"assistant","message":{"model":"claude-opus-4-8","usage":{"input_tokens":10,"output_tokens":1},"content":[{"type":"tool_use","id":"u1","name":"Skill","input":{"skill":"dev-team:plan"}}]}}
{"type":"assistant","message":{"content":[{"type":"tool_use","id":"u2","name":"Skill","input":{"skill":"dev-team:plan"}}]}}
{"type":"assistant","message":{"content":[{"type":"tool_use","id":"u3","name":"Agent","input":{"subagent_type":"dev-team:software-engineer","description":"x"}}]}}
{"type":"assistant","message":{"content":[{"type":"tool_use","id":"u4","name":"Skill","input":{"skill":"update-config"}}]}}
EOF
  run python3 "$EXTRACT" --transcript "$TMP/t.jsonl" --plugin-root "$PLUGIN"
  [ "$status" -eq 0 ]
  # namespace stripped so it matches the registry
  [ "$(echo "$output" | jq -r '.utilization.skills_invoked.plan')" = "2" ]
  [ "$(echo "$output" | jq -r '.utilization.agents_invoked."software-engineer"')" = "1" ]
  # other-plugin skill kept as-is
  [ "$(echo "$output" | jq -r '.utilization.skills_invoked."update-config"')" = "1" ]
  # an invoked skill is NOT in never-observed
  [ "$(echo "$output" | jq -r '.utilization.never_observed_skills | index("plan")')" = "null" ]
}

# ---- #178: rollup union read --------------------------------------------
_seed_digests() {
  mkdir -p "$TMP/digests/boxA" "$TMP/digests/boxB"
  cat > "$TMP/digests/boxA/session-digest.jsonl" <<'EOF'
{"schema":"session-sync/v1","host":"boxA","project":"alpha","session_id":"s1","tokens":{"input_tokens":1000,"output_tokens":100,"cache_read_input_tokens":400},"cost_usd":0.5,"rework":{"failed_edits":1},"accuracy":{"tool_calls":10,"tool_error_rate":0.1,"user_correction_turns":1},"utilization":{"skills_invoked":{"plan":1},"agents_invoked":{}}}
{"schema":"session-sync/v1","host":"boxA","project":"beta","session_id":"s2","tokens":{"input_tokens":2000,"output_tokens":200},"cost_usd":1.0,"rework":{"failed_edits":0},"accuracy":{"tool_calls":5,"tool_error_rate":0.0,"user_correction_turns":0},"utilization":{"skills_invoked":{},"agents_invoked":{"software-engineer":1}}}
EOF
  cat > "$TMP/digests/boxB/session-digest.jsonl" <<'EOF'
{"schema":"session-sync/v1","host":"boxB","project":"alpha","session_id":"s3","tokens":{"input_tokens":500,"output_tokens":50},"cost_usd":0.25,"rework":{"failed_edits":2},"accuracy":{"tool_calls":4,"tool_error_rate":0.25,"user_correction_turns":0},"utilization":{"skills_invoked":{"plan":2},"agents_invoked":{}}}
EOF
}

@test "rollup: aggregates sessions/tokens/cost across hosts and projects (#178)" {
  _seed_digests
  run python3 "$EXTRACT" --rollup "$TMP/digests" --plugin-root "$PLUGIN"
  [ "$status" -eq 0 ]
  [ "$(echo "$output" | jq -r '.sessions')" = "3" ]
  [ "$(echo "$output" | jq -r '.hosts | join(",")')" = "boxA,boxB" ]
  [ "$(echo "$output" | jq -r '.projects | join(",")')" = "alpha,beta" ]
  [ "$(echo "$output" | jq -r '.tokens.input_tokens')" = "3500" ]
  [ "$(echo "$output" | jq -r '.cost_usd')" = "1.75" ]
  [ "$(echo "$output" | jq -r '.cache_hit_ratio')" = "1.0" ]
}

@test "rollup: by_host and by_project breakdowns (#178)" {
  _seed_digests
  run python3 "$EXTRACT" --rollup "$TMP/digests" --plugin-root "$PLUGIN"
  [ "$(echo "$output" | jq -r '.by_host.boxA.sessions')" = "2" ]
  [ "$(echo "$output" | jq -r '.by_host.boxB.sessions')" = "1" ]
  [ "$(echo "$output" | jq -r '.by_project.alpha.sessions')" = "2" ]
  [ "$(echo "$output" | jq -r '.by_project.beta.sessions')" = "1" ]
}

@test "rollup: utilization unions invocations + never-observed across all hosts (#178)" {
  _seed_digests
  run python3 "$EXTRACT" --rollup "$TMP/digests" --plugin-root "$PLUGIN"
  # plan invoked on both hosts: 1 + 2
  [ "$(echo "$output" | jq -r '.utilization.skills_invoked.plan')" = "3" ]
  [ "$(echo "$output" | jq -r '.utilization.agents_invoked."software-engineer"')" = "1" ]
  # a skill invoked on ANY host is not in the cross-machine never-observed set
  [ "$(echo "$output" | jq -r '.utilization.never_observed_skills | index("plan")')" = "null" ]
  [ "$(echo "$output" | jq -r '.utilization.never_observed_skills | length > 5')" = "true" ]
}

@test "rollup: a session_id seen twice is deduped (#178)" {
  _seed_digests
  # boxB re-emits s1 (e.g. grown) -> must count once, not twice
  echo '{"schema":"session-sync/v1","host":"boxB","project":"alpha","session_id":"s1","tokens":{"input_tokens":9999,"output_tokens":1},"cost_usd":9.9,"rework":{},"accuracy":{"tool_calls":1,"tool_error_rate":0,"user_correction_turns":0},"utilization":{"skills_invoked":{},"agents_invoked":{}}}' \
    >> "$TMP/digests/boxB/session-digest.jsonl"
  run python3 "$EXTRACT" --rollup "$TMP/digests" --plugin-root "$PLUGIN"
  # still 3 unique sessions (s1 deduped, last write wins)
  [ "$(echo "$output" | jq -r '.sessions')" = "3" ]
}

@test "rollup: empty/missing dir yields a well-formed empty rollup (#178)" {
  run python3 "$EXTRACT" --rollup "$TMP/nope" --plugin-root "$PLUGIN"
  [ "$status" -eq 0 ]
  [ "$(echo "$output" | jq -r '.sessions')" = "0" ]
}

# ---- #171: --cost-log per-session cost series for the regression gate ----
_seed_cost_digests() {
  mkdir -p "$TMP/digests/boxA" "$TMP/digests/boxB"
  # ts deliberately out of file order; cost-log must sort oldest->newest by ts.
  cat > "$TMP/digests/boxA/session-digest.jsonl" <<'EOF'
{"schema":"session-sync/v1","host":"boxA","session_id":"s2","ts":"2026-06-02T00:00:00Z","cost_usd":2.0}
{"schema":"session-sync/v1","host":"boxA","session_id":"s1","ts":"2026-06-01T00:00:00Z","cost_usd":1.0}
EOF
  cat > "$TMP/digests/boxB/session-digest.jsonl" <<'EOF'
{"schema":"session-sync/v1","host":"boxB","session_id":"s3","ts":"2026-06-03T00:00:00Z","cost_usd":3.0}
EOF
}

@test "cost-log: emits a ts-ordered per-session cost series across hosts (#171)" {
  _seed_cost_digests
  run python3 "$EXTRACT" --cost-log "$TMP/digests" --plugin-root "$PLUGIN"
  [ "$status" -eq 0 ]
  # three records, oldest first, in cost-meter shape
  [ "$(echo "$output" | wc -l | tr -d ' ')" = "3" ]
  [ "$(echo "$output" | jq -s 'map(.total.cost_usd) == [1,2,3]')" = "true" ]
  [ "$(echo "$output" | head -1 | jq -r '.ts')" = "2026-06-01T00:00:00Z" ]
}

@test "cost-log: dedups a session_id seen twice, last write wins (#171)" {
  _seed_cost_digests
  # re-emit s1 with a higher cost -> one record, newest value
  echo '{"schema":"session-sync/v1","host":"boxB","session_id":"s1","ts":"2026-06-01T00:00:00Z","cost_usd":5.0}' \
    >> "$TMP/digests/boxB/session-digest.jsonl"
  run python3 "$EXTRACT" --cost-log "$TMP/digests" --plugin-root "$PLUGIN"
  [ "$(echo "$output" | wc -l | tr -d ' ')" = "3" ]
  [ "$(echo "$output" | jq -s 'map(.total.cost_usd) == [5,2,3]')" = "true" ]
}

@test "cost-log: empty/missing dir yields no records, clean exit (#171)" {
  run python3 "$EXTRACT" --cost-log "$TMP/nope" --plugin-root "$PLUGIN"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}
