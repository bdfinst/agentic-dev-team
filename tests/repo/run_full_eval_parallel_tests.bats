#!/usr/bin/env bats
# run-full-eval-parallel.sh — guards the DETERMINISTIC reconciliation, the only
# correctness-critical logic the parallel harness adds (dispatch itself needs live
# models and isn't unit-tested). Two invariants:
#   1. The jq deep-merge of per-agent FIRST trials is a loss-free union when agents
#      are disjoint — even when two agents grade the SAME fixture stem.
#   2. The grade is scoped (--only) to agents that produced actuals, so an agent
#      that failed to dispatch keeps its existing baseline pairs (no wipe).

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
GRADE="$REPO_ROOT/scripts/eval_grade.py"

setup() {
  TMP="$(mktemp -d)"
}
teardown() {
  rm -rf "$TMP"
}

# The exact merge the script runs to union per-agent first trials.
merge_actuals() {
  jq -s 'reduce .[] as $x ({}; . * $x)' "$@"
}

@test "disjoint-agent trials union without loss (same stem, different agents)" {
  # Two batches each produced one agent's actuals for the SAME fixture stem.
  cat > "$TMP/a.json" <<'EOF'
{"shared":{"agents":{"agent-a":{"status":"pass","issues":[]}}}}
EOF
  cat > "$TMP/b.json" <<'EOF'
{"shared":{"agents":{"agent-b":{"status":"fail","issues":[]}}}}
EOF
  merge_actuals "$TMP/a.json" "$TMP/b.json" > "$TMP/out.json"
  # Both agents survive under the shared stem — recursive merge, not clobber.
  run jq -r '.shared.agents | keys | join(",")' "$TMP/out.json"
  [ "$status" -eq 0 ]
  [ "$output" = "agent-a,agent-b" ]
  run jq -r '.shared.agents."agent-a".status' "$TMP/out.json"
  [ "$output" = "pass" ]
  run jq -r '.shared.agents."agent-b".status' "$TMP/out.json"
  [ "$output" = "fail" ]
}

@test "merge of separate stems keeps every stem" {
  echo '{"s1":{"agents":{"a":{"status":"pass","issues":[]}}}}' > "$TMP/a.json"
  echo '{"s2":{"agents":{"b":{"status":"pass","issues":[]}}}}' > "$TMP/b.json"
  merge_actuals "$TMP/a.json" "$TMP/b.json" > "$TMP/out.json"
  run jq -r 'keys | join(",")' "$TMP/out.json"
  [ "$output" = "s1,s2" ]
}

@test "scoped grade leaves an un-dispatched agent's baseline pairs untouched" {
  # Corpus: two pairs, one per agent.
  mkdir -p "$TMP/expected"
  cat > "$TMP/expected/clean.json" <<'EOF'
{"fixture":"clean.ts","applicableAgents":["agent-a"],"agents":{"agent-a":{"expectedStatus":"pass","issueCount":{"min":0,"max":0}}}}
EOF
  cat > "$TMP/expected/other.json" <<'EOF'
{"fixture":"other.ts","applicableAgents":["agent-b"],"agents":{"agent-b":{"expectedStatus":"pass","issueCount":{"min":0,"max":0}}}}
EOF
  # Pre-existing baseline says agent-b's pair already passes.
  cat > "$TMP/baseline.json" <<'EOF'
{"_comment":"x","provenance":"measured","recorded_at":"2026-01-01T00:00:00Z","passing":["other::agent-b"]}
EOF
  # This harvest only produced actuals for agent-a (agent-b failed to dispatch).
  cat > "$TMP/actuals.json" <<'EOF'
{"clean":{"agents":{"agent-a":{"status":"pass","issues":[]}}}}
EOF
  run python3 "$GRADE" --expected-dir "$TMP/expected" --actuals "$TMP/actuals.json" \
    --only "agent-a" --write-baseline "$TMP/baseline.json"
  [ "$status" -eq 0 ]
  # agent-b's pair must SURVIVE (scoped grade never tested it); agent-a's added.
  run jq -r '.passing | sort | join(",")' "$TMP/baseline.json"
  [ "$output" = "clean::agent-a,other::agent-b" ]
}
