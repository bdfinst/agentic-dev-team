#!/usr/bin/env bats
# #103 — eval variance aggregator: pass@k, flap detection, quarantine. Model-free
# (synthetic per-trial actuals), so it runs in CI like the rest of the grader.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
VAR="$REPO_ROOT/scripts/eval_variance.py"

setup() {
  TMP="$(mktemp -d)"
  mkdir -p "$TMP/expected" "$TMP/trials"
  # Two pairs: stable-pass (clean::a) and flapping (flap::b).
  cat > "$TMP/expected/clean.json" <<'EOF'
{"fixture":"clean.ts","applicableAgents":["a"],"agents":{"a":{"expectedStatus":"pass","issueCount":{"min":0,"max":0}}}}
EOF
  cat > "$TMP/expected/flap.json" <<'EOF'
{"fixture":"flap.ts","applicableAgents":["b"],"agents":{"b":{"expectedStatus":"pass","issueCount":{"min":0,"max":0}}}}
EOF
  # Trial 1: both pass.
  cat > "$TMP/trials/t1.json" <<'EOF'
{"clean":{"agents":{"a":{"status":"pass","issues":[]}}},"flap":{"agents":{"b":{"status":"pass","issues":[]}}}}
EOF
  # Trial 2: clean passes, flap FAILS (wrong status).
  cat > "$TMP/trials/t2.json" <<'EOF'
{"clean":{"agents":{"a":{"status":"pass","issues":[]}}},"flap":{"agents":{"b":{"status":"fail","issues":[]}}}}
EOF
}
teardown() { rm -rf "$TMP"; }

_run() { python3 "$VAR" --trials-dir "$TMP/trials" --expected-dir "$TMP/expected"; }

@test "variance: pass@k computed per pair" {
  run _run
  [ "$status" -eq 0 ]
  [ "$(echo "$output" | jq -r '.trials')" = "2" ]
  [ "$(echo "$output" | jq -r '.by_pair."clean::a".pass_at_k')" = "1.0" ]
  [ "$(echo "$output" | jq -r '.by_pair."flap::b".pass_at_k')" = "0.5" ]
}

@test "variance: a flapping pair is flagged and quarantined" {
  run _run
  [ "$(echo "$output" | jq -r '.by_pair."flap::b".flap')" = "true" ]
  [ "$(echo "$output" | jq -r '.by_pair."clean::a".flap')" = "false" ]
  [ "$(echo "$output" | jq -r '.flaky_count')" = "1" ]
  [ "$(echo "$output" | jq -r '.quarantine | index("flap::b")')" != "null" ]
}

@test "variance: per-agent stability summary" {
  run _run
  [ "$(echo "$output" | jq -r '.by_agent.a.mean_pass_at_k')" = "1.0" ]
  [ "$(echo "$output" | jq -r '.by_agent.b.flaky_fixtures')" = "1" ]
}

@test "variance: --append writes a metrics-only trend record" {
  python3 "$VAR" --trials-dir "$TMP/trials" --expected-dir "$TMP/expected" \
    --append "$TMP/trend.jsonl" >/dev/null
  [ "$(wc -l < "$TMP/trend.jsonl")" -eq 1 ]
  [ "$(jq -r '.flaky_count' "$TMP/trend.jsonl")" = "1" ]
  # metrics only — no fixture/agent names in the trend record
  run cat "$TMP/trend.jsonl"
  [[ "$output" != *"flap::b"* ]]
}
