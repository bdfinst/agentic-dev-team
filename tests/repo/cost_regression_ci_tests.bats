#!/usr/bin/env bats
# Tests for scripts/cost-regression-check.sh — the CI wiring for the cost-meter
# regression gate (#140): self-test (blocking), committed baseline (warn-only),
# and no-baseline (clean pass).

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
CHECK="$REPO_ROOT/scripts/cost-regression-check.sh"

setup() { WORK="$(mktemp -d)"; }
teardown() { rm -rf "$WORK"; }

@test "ci-cost: self-test passes and no baseline -> clean exit 0" {
  run env COST_BASELINE_LOG="$WORK/none.jsonl" bash "$CHECK"
  [ "$status" -eq 0 ]
  [[ "$output" == *"spike flagged, within-tolerance passes"* ]]
  [[ "$output" == *"no committed baseline"* ]]
}

@test "ci-cost: a committed baseline with a spike warns but does NOT block" {
  printf '%s\n' '{"total":{"cost_usd":1.0}}' '{"total":{"cost_usd":1.0}}' \
    '{"total":{"cost_usd":9.0}}' > "$WORK/base.jsonl"
  run env COST_BASELINE_LOG="$WORK/base.jsonl" COST_TOLERANCE=0.5 bash "$CHECK"
  [ "$status" -eq 0 ]                       # warn-only: never blocks
  [[ "$output" == *"COST REGRESSION"* ]]
  [[ "$output" == *"::warning"* ]]
}

@test "ci-cost: a within-tolerance baseline passes without a warning" {
  printf '%s\n' '{"total":{"cost_usd":1.0}}' '{"total":{"cost_usd":1.1}}' \
    > "$WORK/base.jsonl"
  run env COST_BASELINE_LOG="$WORK/base.jsonl" COST_TOLERANCE=0.5 bash "$CHECK"
  [ "$status" -eq 0 ]
  [[ "$output" == *"no cost regression"* ]]
  [[ "$output" != *"::warning"* ]]
}

@test "ci-cost: registered as a step in plugin-tests.yml" {
  grep -q "cost-regression-check.sh" "$REPO_ROOT/.github/workflows/plugin-tests.yml"
}
