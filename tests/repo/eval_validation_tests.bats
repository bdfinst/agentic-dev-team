#!/usr/bin/env bats
# Eval validation gap — Phase 1 (#229/#230/#231). Trust-gated baseline writes and
# quarantine consumption. Model-free (synthetic per-trial actuals), so it runs in
# CI like the rest of the grader.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
VAR="$REPO_ROOT/scripts/eval_variance.py"
GRADE="$REPO_ROOT/scripts/eval_grade.py"

setup() {
  TMP="$(mktemp -d)"
  mkdir -p "$TMP/expected" "$TMP/trials"
  # One single-agent fixture per agent so pairs are <stem>::<agent>.
  for stem in a b c d; do
    cat > "$TMP/expected/$stem.json" <<EOF
{"fixture":"$stem.ts","applicableAgents":["ag-$stem"],"agents":{"ag-$stem":{"expectedStatus":"pass","issueCount":{"min":0,"max":0}}}}
EOF
    mkdir -p "$TMP/trials/ag-$stem"
  done
}
teardown() { rm -rf "$TMP"; }

# Write N trials for agent ag-$stem on fixture $stem with the given status each.
# usage: trials <stem> <status1> <status2> ...
trials() {
  local stem="$1"; shift; local n=0
  for st in "$@"; do
    n=$((n + 1))
    echo "{\"$stem\":{\"agents\":{\"ag-$stem\":{\"status\":\"$st\",\"issues\":[]}}}}" \
      > "$TMP/trials/ag-$stem/trial-$n.json"
  done
}

run_baseline() {  # run_baseline <only-csv> [extra args...]
  python3 "$VAR" --trials-root "$TMP/trials" --only "$1" --expected-dir "$TMP/expected" \
    --write-baseline "$TMP/baseline.json" --quarantine-out "$TMP/quarantine.json" "${@:2}"
}

@test "all-pass pair is added to the baseline" {
  trials a pass pass pass
  echo '{"passing":[]}' > "$TMP/baseline.json"
  run run_baseline "ag-a"
  [ "$status" -eq 0 ]
  run jq -r '.passing | join(",")' "$TMP/baseline.json"
  [ "$output" = "a::ag-a" ]
}

@test "consistently-failing pair (pass@k 0 over >= min_trials) is removed" {
  trials b fail fail fail
  echo '{"passing":["b::ag-b"]}' > "$TMP/baseline.json"
  run run_baseline "ag-b"
  [ "$status" -eq 0 ]
  run jq -r '.passing | length' "$TMP/baseline.json"
  [ "$output" = "0" ]
}

@test "single-trial failure does NOT delete (trials < min_trials) — the -9 fix" {
  trials b fail               # exactly one trial
  echo '{"passing":["b::ag-b"]}' > "$TMP/baseline.json"
  run run_baseline "ag-b"
  [ "$status" -eq 0 ]
  run jq -r '.passing | join(",")' "$TMP/baseline.json"
  [ "$output" = "b::ag-b" ]   # survived the noisy single sample
}

@test "flaky pair is quarantined and NOT removed" {
  trials c pass pass fail      # 2/3 -> flaky
  echo '{"passing":["c::ag-c"]}' > "$TMP/baseline.json"
  run run_baseline "ag-c"
  [ "$status" -eq 0 ]
  run jq -r '.passing | join(",")' "$TMP/baseline.json"
  [ "$output" = "c::ag-c" ]                       # kept
  run jq -r '.quarantine | join(",")' "$TMP/quarantine.json"
  [ "$output" = "c::ag-c" ]                       # and quarantined
}

@test "per-agent scoping leaves an un-run agent's baseline pairs untouched" {
  trials a pass pass pass                          # only ag-a runs
  echo '{"passing":["d::ag-d"]}' > "$TMP/baseline.json"
  run run_baseline "ag-a"
  [ "$status" -eq 0 ]
  run jq -r '.passing | sort | join(",")' "$TMP/baseline.json"
  [ "$output" = "a::ag-a,d::ag-d" ]                # d untouched, a added
}

@test "grader excludes quarantined pairs from blocking (#231)" {
  # c is flaky+quarantined and in the baseline; a fresh run where it fails again
  # must NOT block the gate.
  echo '{"passing":["c::ag-c"]}' > "$TMP/baseline.json"
  echo '{"quarantine":["c::ag-c"]}' > "$TMP/quarantine.json"
  echo '{"c":{"agents":{"ag-c":{"status":"fail","issues":[]}}}}' > "$TMP/run.json"
  run python3 "$GRADE" --expected-dir "$TMP/expected" --actuals "$TMP/run.json" \
    --baseline "$TMP/baseline.json" --quarantine "$TMP/quarantine.json" --only ag-c
  [ "$status" -eq 0 ]
}

@test "harvest-id is stamped into every written artifact (#232 provenance)" {
  trials a pass pass pass
  echo '{"passing":[]}' > "$TMP/baseline.json"
  run python3 "$VAR" --trials-root "$TMP/trials" --only ag-a --expected-dir "$TMP/expected" \
    --harvest-id "H-123" --write-baseline "$TMP/baseline.json" \
    -o "$TMP/variance.json" --quarantine-out "$TMP/quarantine.json"
  [ "$status" -eq 0 ]
  [ "$(jq -r '.harvest_id' "$TMP/baseline.json")" = "H-123" ]
  [ "$(jq -r '.harvest_id' "$TMP/variance.json")" = "H-123" ]
  [ "$(jq -r '.harvest_id' "$TMP/quarantine.json")" = "H-123" ]
}

@test "grader still blocks a real (non-quarantined) regression" {
  echo '{"passing":["c::ag-c"]}' > "$TMP/baseline.json"
  echo '{"quarantine":[]}' > "$TMP/quarantine.json"
  echo '{"c":{"agents":{"ag-c":{"status":"fail","issues":[]}}}}' > "$TMP/run.json"
  run python3 "$GRADE" --expected-dir "$TMP/expected" --actuals "$TMP/run.json" \
    --baseline "$TMP/baseline.json" --quarantine "$TMP/quarantine.json" --only ag-c
  [ "$status" -eq 1 ]
}
