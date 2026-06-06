#!/usr/bin/env bats
# Tests for cost_meter.py `pace` — account-level budget pace guidance (#142).

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
METER="$REPO_ROOT/plugins/dev-team/hooks/lib/cost_meter.py"

setup() { CASE="$(mktemp -d)"; }
teardown() { rm -rf "$CASE"; }

# A timestamp N days before now, in the meter's ISO format.
_ts() { date -u -d "$1 days ago" +%Y-%m-%dT%H:%M:%SZ; }

@test "pace: no log -> says nothing to pace" {
  run python3 "$METER" pace --log "$CASE/none.jsonl"
  [ "$status" -eq 0 ]
  [[ "$output" == *"nothing to pace"* ]]
}

@test "pace: reports cumulative spend over the window" {
  {
    echo "{\"timestamp\":\"$(_ts 2)\",\"total\":{\"cost_usd\":10.0}}"
    echo "{\"timestamp\":\"$(_ts 1)\",\"total\":{\"cost_usd\":5.0}}"
  } > "$CASE/log.jsonl"
  run python3 "$METER" pace --log "$CASE/log.jsonl" --window-days 7
  [ "$status" -eq 0 ]
  [[ "$output" == *"cumulative spend:   \$15.0000"* ]]
}

@test "pace: flags when projected spend exceeds the budget" {
  # ~\$25/day over 2 days -> projected ~\$750/30d, well past a \$100 budget.
  {
    echo "{\"timestamp\":\"$(_ts 2)\",\"total\":{\"cost_usd\":30.0}}"
    echo "{\"timestamp\":\"$(_ts 1)\",\"total\":{\"cost_usd\":20.0}}"
  } > "$CASE/log.jsonl"
  run python3 "$METER" pace --log "$CASE/log.jsonl" --budget 100 --period-days 30 --window-days 7
  [ "$status" -eq 0 ]
  [[ "$output" == *"PACE EXCEEDS BUDGET"* ]]
  [[ "$output" == *"Opus→Sonnet"* ]]
}

@test "pace: within budget does not flag" {
  # \$0.10 total over 2 days -> projected ~\$1.5/30d, well under a \$100 budget.
  {
    echo "{\"timestamp\":\"$(_ts 2)\",\"total\":{\"cost_usd\":0.05}}"
    echo "{\"timestamp\":\"$(_ts 1)\",\"total\":{\"cost_usd\":0.05}}"
  } > "$CASE/log.jsonl"
  run python3 "$METER" pace --log "$CASE/log.jsonl" --budget 100 --period-days 30 --window-days 7
  [ "$status" -eq 0 ]
  [[ "$output" != *"PACE EXCEEDS BUDGET"* ]]
}

@test "pace: entries older than the window are excluded" {
  {
    echo "{\"timestamp\":\"$(_ts 30)\",\"total\":{\"cost_usd\":999.0}}"
    echo "{\"timestamp\":\"$(_ts 1)\",\"total\":{\"cost_usd\":5.0}}"
  } > "$CASE/log.jsonl"
  run python3 "$METER" pace --log "$CASE/log.jsonl" --window-days 7
  [ "$status" -eq 0 ]
  [[ "$output" == *"cumulative spend:   \$5.0000"* ]]
  [[ "$output" == *"sessions in window: 1"* ]]
}
