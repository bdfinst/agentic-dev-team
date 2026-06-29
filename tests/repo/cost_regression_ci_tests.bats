#!/usr/bin/env bats
# Tests for scripts/cost-regression-check.sh — the CI wiring for the cost-meter
# regression gate (#140 mechanism, #171 real cross-machine baseline): self-test
# (blocking), real baseline (warn-only), and no-baseline (clean pass).

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
CHECK="$REPO_ROOT/scripts/cost-regression-check.sh"
EXTRACT="$REPO_ROOT/scripts/session_extract.py"

setup() { WORK="$(mktemp -d)"; }
teardown() { rm -rf "$WORK"; }

@test "ci-cost: self-test passes and no baseline -> clean exit 0" {
  run env COST_BASELINE_LOG="$WORK/none.jsonl" bash "$CHECK"
  [ "$status" -eq 0 ]
  [[ "$output" == *"spike flagged, within-tolerance passes"* ]]
  [[ "$output" == *"no baseline log"* ]]
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

@test "ci-cost: #171 end-to-end — telemetry digests -> cost-log baseline -> warn" {
  # Simulate the CI flow: a cloned telemetry repo's digests become the baseline.
  mkdir -p "$WORK/digests/boxA"
  cat > "$WORK/digests/boxA/session-digest.jsonl" <<'EOF'
{"schema":"session-sync/v1","host":"boxA","session_id":"s1","ts":"2026-06-01T00:00:00Z","cost_usd":1.0}
{"schema":"session-sync/v1","host":"boxA","session_id":"s2","ts":"2026-06-02T00:00:00Z","cost_usd":1.0}
{"schema":"session-sync/v1","host":"boxA","session_id":"s3","ts":"2026-06-03T00:00:00Z","cost_usd":9.0}
EOF
  python3 "$EXTRACT" --cost-log "$WORK/digests" -o "$WORK/cost-log.jsonl"
  # newest session (ts 06-03) is the spike; priors mean to 1.0
  run env COST_BASELINE_LOG="$WORK/cost-log.jsonl" COST_TOLERANCE=0.5 bash "$CHECK"
  [ "$status" -eq 0 ]                       # warn-only: never blocks
  [[ "$output" == *"COST REGRESSION"* ]]
  [[ "$output" == *"::warning"* ]]
}

@test "ci-cost: registered as a step in plugin-tests.yml" {
  # Wired either directly or through the shared gate (scripts/ci-local.sh's
  # chk_cost_regression — single source of truth for CI and pre-push). For the
  # indirect form, confirm ci-local actually maps the check to the script.
  local wf="$REPO_ROOT/.github/workflows/plugin-tests.yml"
  if grep -q "cost-regression-check.sh" "$wf"; then
    return 0
  fi
  grep -q "chk_cost_regression" "$wf" \
    && grep -q "chk_cost_regression.*cost-regression-check.sh" "$REPO_ROOT/scripts/ci-local.sh"
}
