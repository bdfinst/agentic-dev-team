#!/usr/bin/env bats
# #110 — persona on/off: per-agent pass@k delta, only "real" when it clears the
# variance band (neither run flapped). Model-free core (synthetic on/off trials).

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
PER="$REPO_ROOT/scripts/eval_persona.py"

setup() {
  TMP="$(mktemp -d)"
  mkdir -p "$TMP/expected" "$TMP/on" "$TMP/off"
  cat > "$TMP/expected/f1.json" <<'EOF'
{"fixture":"f1.ts","applicableAgents":["a"],"agents":{"a":{"expectedStatus":"fail","issueCount":{"min":1,"max":3}}}}
EOF
  cat > "$TMP/expected/f2.json" <<'EOF'
{"fixture":"f2.ts","applicableAgents":["a"],"agents":{"a":{"expectedStatus":"fail","issueCount":{"min":1,"max":3}}}}
EOF
  _t() { echo "{\"f1\":{\"agents\":{\"a\":{\"status\":\"$1\",\"issues\":$3}}},\"f2\":{\"agents\":{\"a\":{\"status\":\"$2\",\"issues\":$4}}}}"; }
  ISS='[{"severity":"warning","message":"x"}]'
}
teardown() { rm -rf "$TMP"; }

@test "persona: a real, non-flapping delta is reported as added value" {
  ISS='[{"severity":"warning","message":"x"}]'
  # ON: both fixtures pass (fail status w/ 1 issue) in both trials -> mean 1.0
  for n in 1 2; do echo "{\"f1\":{\"agents\":{\"a\":{\"status\":\"fail\",\"issues\":$ISS}}},\"f2\":{\"agents\":{\"a\":{\"status\":\"fail\",\"issues\":$ISS}}}}" > "$TMP/on/t$n.json"; done
  # OFF: f1 passes, f2 always wrong status (pass) -> stable fail -> mean 0.5, no flap
  for n in 1 2; do echo "{\"f1\":{\"agents\":{\"a\":{\"status\":\"fail\",\"issues\":$ISS}}},\"f2\":{\"agents\":{\"a\":{\"status\":\"pass\",\"issues\":[]}}}}" > "$TMP/off/t$n.json"; done
  run python3 "$PER" --on-trials "$TMP/on" --off-trials "$TMP/off" --expected-dir "$TMP/expected"
  [ "$status" -eq 0 ]
  [ "$(echo "$output" | jq -r '.by_agent.a.delta')" = "0.5" ]
  [ "$(echo "$output" | jq -r '.by_agent.a.real')" = "true" ]
  [ "$(echo "$output" | jq -r '.persona_helps')" = "1" ]
}

@test "persona: identical on/off is an honest null (no effect)" {
  ISS='[{"severity":"warning","message":"x"}]'
  for d in on off; do for n in 1 2; do echo "{\"f1\":{\"agents\":{\"a\":{\"status\":\"fail\",\"issues\":$ISS}}},\"f2\":{\"agents\":{\"a\":{\"status\":\"fail\",\"issues\":$ISS}}}}" > "$TMP/$d/t$n.json"; done; done
  run python3 "$PER" --on-trials "$TMP/on" --off-trials "$TMP/off" --expected-dir "$TMP/expected"
  [ "$(echo "$output" | jq -r '.by_agent.a.delta')" = "0.0" ]
  [ "$(echo "$output" | jq -r '.by_agent.a.real')" = "false" ]
  [[ "$(echo "$output" | jq -r '.by_agent.a.verdict')" == *"no effect"* ]]
}

@test "persona: a flapping run marks the delta as within-noise, not real (#110)" {
  ISS='[{"severity":"warning","message":"x"}]'
  for n in 1 2; do echo "{\"f1\":{\"agents\":{\"a\":{\"status\":\"fail\",\"issues\":$ISS}}},\"f2\":{\"agents\":{\"a\":{\"status\":\"fail\",\"issues\":$ISS}}}}" > "$TMP/on/t$n.json"; done
  # OFF flaps on f2 (pass then fail) -> flaky -> delta is within noise band
  echo "{\"f1\":{\"agents\":{\"a\":{\"status\":\"fail\",\"issues\":$ISS}}},\"f2\":{\"agents\":{\"a\":{\"status\":\"fail\",\"issues\":$ISS}}}}" > "$TMP/off/t1.json"
  echo "{\"f1\":{\"agents\":{\"a\":{\"status\":\"fail\",\"issues\":$ISS}}},\"f2\":{\"agents\":{\"a\":{\"status\":\"pass\",\"issues\":[]}}}}" > "$TMP/off/t2.json"
  run python3 "$PER" --on-trials "$TMP/on" --off-trials "$TMP/off" --expected-dir "$TMP/expected"
  [ "$(echo "$output" | jq -r '.by_agent.a.flapped')" = "true" ]
  [ "$(echo "$output" | jq -r '.by_agent.a.real')" = "false" ]
  [[ "$(echo "$output" | jq -r '.by_agent.a.verdict')" == *"noise"* ]]
}
