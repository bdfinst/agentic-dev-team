#!/usr/bin/env bats
# #107 — knowledge ablation: pairs that pass WITH a knowledge file but fail
# WITHOUT it = its retrieval value. Model-free core (synthetic with/without
# actuals), matching the positive/negative controls in the verification plan.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
ABL="$REPO_ROOT/scripts/eval_ablation.py"

setup() {
  TMP="$(mktemp -d)"
  mkdir -p "$TMP/expected"
  cat > "$TMP/expected/dep.json" <<'EOF'
{"fixture":"dep.ts","applicableAgents":["a"],"agents":{"a":{"expectedStatus":"fail","issueCount":{"min":1,"max":3},"mustMention":["smell"]}}}
EOF
  cat > "$TMP/expected/indep.json" <<'EOF'
{"fixture":"indep.ts","applicableAgents":["a"],"agents":{"a":{"expectedStatus":"pass","issueCount":{"min":0,"max":0}}}}
EOF
  # WITH knowledge: both pairs pass.
  cat > "$TMP/with.json" <<'EOF'
{"dep":{"agents":{"a":{"status":"fail","issues":[{"severity":"warning","message":"a smell"}],"summary":"smell found"}}},
 "indep":{"agents":{"a":{"status":"pass","issues":[],"summary":"clean"}}}}
EOF
  # WITHOUT the knowledge: dep::a misses the smell (now passes -> wrong status),
  # indep::a unchanged.
  cat > "$TMP/without.json" <<'EOF'
{"dep":{"agents":{"a":{"status":"pass","issues":[],"summary":"looks fine"}}},
 "indep":{"agents":{"a":{"status":"pass","issues":[],"summary":"clean"}}}}
EOF
}
teardown() { rm -rf "$TMP"; }

@test "ablation: a load-bearing file's removal drops the dependent pair (positive control)" {
  run python3 "$ABL" --expected-dir "$TMP/expected" \
    --baseline "$TMP/with.json" --ablated "$TMP/without.json" --knowledge test-smells.md
  [ "$status" -eq 0 ]
  [ "$(echo "$output" | jq -r '.retrieval_value')" = "1" ]
  [ "$(echo "$output" | jq -r '.dropped_pairs[0]')" = "dep::a" ]
  [[ "$(echo "$output" | jq -r '.verdict')" == *"earns its place"* ]]
}

@test "ablation: an irrelevant file's removal changes nothing (negative control)" {
  # ablated == baseline -> no pair drops
  run python3 "$ABL" --expected-dir "$TMP/expected" \
    --baseline "$TMP/with.json" --ablated "$TMP/with.json" --knowledge unrelated.md
  [ "$status" -eq 0 ]
  [ "$(echo "$output" | jq -r '.retrieval_value')" = "0" ]
  [[ "$(echo "$output" | jq -r '.verdict')" == *"no measured impact"* ]]
}

@test "ablation: the unrelated pair never drops even when a file is load-bearing" {
  run python3 "$ABL" --expected-dir "$TMP/expected" \
    --baseline "$TMP/with.json" --ablated "$TMP/without.json"
  # indep::a stays passing in both -> not in dropped
  [ "$(echo "$output" | jq -r '.dropped_pairs | index("indep::a")')" = "null" ]
}
