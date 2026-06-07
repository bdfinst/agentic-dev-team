#!/usr/bin/env bats
# run-full-eval-parallel.sh — guards the DETERMINISTIC reconciliation the parallel
# harness performs. Since #230/#231 the reconcile is a single `eval_variance
# --trials-root` pass over each agent's k trials (the unit rules live in
# eval_validation_tests.bats); this file asserts the end-to-end harness command
# produces all three trust-rated artifacts from a synthetic per-agent pool, and
# that scoping protects un-run agents. Model-free, so it runs in CI.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
VAR="$REPO_ROOT/scripts/eval_variance.py"

setup() {
  TMP="$(mktemp -d)"
  mkdir -p "$TMP/expected" "$TMP/pool/agent-a" "$TMP/pool/agent-b"
  cat > "$TMP/expected/clean.json" <<'EOF'
{"fixture":"clean.ts","applicableAgents":["agent-a"],"agents":{"agent-a":{"expectedStatus":"pass","issueCount":{"min":0,"max":0}}}}
EOF
  cat > "$TMP/expected/other.json" <<'EOF'
{"fixture":"other.ts","applicableAgents":["agent-b"],"agents":{"agent-b":{"expectedStatus":"pass","issueCount":{"min":0,"max":0}}}}
EOF
  # agent-a: 3/3 pass on clean; agent-b: 3/3 fail on other (was passing).
  for n in 1 2 3; do
    echo '{"clean":{"agents":{"agent-a":{"status":"pass","issues":[]}}}}' > "$TMP/pool/agent-a/trial-$n.json"
    echo '{"other":{"agents":{"agent-b":{"status":"fail","issues":[]}}}}' > "$TMP/pool/agent-b/trial-$n.json"
  done
  echo '{"passing":["other::agent-b"]}' > "$TMP/baseline.json"
}
teardown() { rm -rf "$TMP"; }

# The exact reconcile command the harness runs.
reconcile() {  # reconcile <only-csv>
  python3 "$VAR" --trials-root "$TMP/pool" --only "$1" --expected-dir "$TMP/expected" \
    --write-baseline "$TMP/baseline.json" \
    -o "$TMP/variance-report.json" \
    --quarantine-out "$TMP/quarantine.json"
}

@test "reconcile writes all three trust-rated artifacts" {
  run reconcile "agent-a,agent-b"
  [ "$status" -eq 0 ]
  [ -f "$TMP/baseline.json" ]
  [ -f "$TMP/variance-report.json" ]
  [ -f "$TMP/quarantine.json" ]
  run jq -r '.schema' "$TMP/variance-report.json"
  [ "$output" = "eval-variance/v1" ]
}

@test "reconcile adds a solidly-passing agent and removes a consistently-failing one" {
  reconcile "agent-a,agent-b"
  run jq -r '.passing | sort | join(",")' "$TMP/baseline.json"
  [ "$output" = "clean::agent-a" ]   # agent-a added; other::agent-b removed (0/3)
}

@test "an un-run agent's baseline pairs survive the reconcile" {
  # Only agent-a runs; agent-b's prior pair must be left untouched.
  reconcile "agent-a"
  run jq -r '.passing | sort | join(",")' "$TMP/baseline.json"
  [ "$output" = "clean::agent-a,other::agent-b" ]
}
