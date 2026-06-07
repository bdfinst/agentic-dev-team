#!/usr/bin/env bash
# cost-regression-check.sh — CI wiring for the cost-meter regression gate
# (#140 mechanism, #171 real cross-machine baseline).
#
# hooks/lib/cost_meter.py ships a `regression` subcommand, but nothing ran it,
# so a cost regression could merge unnoticed. This wires it into CI with three
# honest behaviors given a non-deterministic meter and a transcript-less runner:
#
#   1. SELF-TEST (blocking). CI has no session transcripts, so we cannot measure
#      this PR's cost. We CAN verify the mechanism still works: a synthetic spike
#      must be flagged (exit 1) and a within-tolerance run must pass (exit 0). If
#      that breaks, the gate is dishonest and CI fails.
#
#   2. REAL BASELINE (warn-only). If COST_BASELINE_LOG points at a cost series,
#      run the real regression check against it. In CI that series is built from
#      the private telemetry repo (the cross-machine per-session costs; #171); a
#      committed metrics/cost-metering.jsonl works too. A non-deterministic meter
#      shouldn't HARD-fail an unrelated code PR, so a detected regression is
#      surfaced as a warning annotation, not a block.
#
#   3. NO BASELINE. If no baseline log is available (e.g. a fork PR with no access
#      to the telemetry repo, or no committed log), say so and pass cleanly.
#
# Tolerance and window are configurable via env (COST_TOLERANCE, COST_WINDOW).
# Exit codes: 0 = ok (incl. warn), 1 = the regression mechanism itself is broken.

set -uo pipefail

cd "$(git rev-parse --show-toplevel)" 2>/dev/null || cd "$(dirname "$0")/.." || exit 1

METER="plugins/dev-team/hooks/lib/cost_meter.py"
BASELINE="${COST_BASELINE_LOG:-metrics/cost-metering.jsonl}"
TOLERANCE="${COST_TOLERANCE:-0.5}"
WINDOW="${COST_WINDOW:-0}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "cost-regression-check: python3 not available; skipping." >&2
  exit 0
fi

# --- 1. self-test (blocking) -------------------------------------------------
echo "== cost-regression self-test =="
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

printf '%s\n' '{"total":{"cost_usd":1.0}}' '{"total":{"cost_usd":1.0}}' \
  '{"total":{"cost_usd":5.0}}' > "$tmp/spike.jsonl"
printf '%s\n' '{"total":{"cost_usd":1.0}}' '{"total":{"cost_usd":1.1}}' \
  > "$tmp/ok.jsonl"

python3 "$METER" regression --log "$tmp/spike.jsonl" --tolerance "$TOLERANCE" >/dev/null 2>&1
spike_rc=$?
python3 "$METER" regression --log "$tmp/ok.jsonl" --tolerance "$TOLERANCE" >/dev/null 2>&1
ok_rc=$?

if [ "$spike_rc" -ne 1 ] || [ "$ok_rc" -ne 0 ]; then
  echo "FAIL: cost-regression mechanism is broken" >&2
  echo "  expected spike->exit 1 (got $spike_rc), within-tolerance->exit 0 (got $ok_rc)" >&2
  exit 1
fi
echo "  ok: spike flagged, within-tolerance passes."

# --- 2/3. real baseline (warn-only) or no baseline ---------------------------
echo "== cost-regression against baseline =="
if [ ! -f "$BASELINE" ]; then
  echo "  no baseline log at $BASELINE — point COST_BASELINE_LOG at a cost series"
  echo "  (CI builds one from the telemetry repo, #171) or commit a local log."
  exit 0
fi

args=(regression --log "$BASELINE" --tolerance "$TOLERANCE")
[ "$WINDOW" -gt 0 ] && args+=(--window "$WINDOW")

out="$(python3 "$METER" "${args[@]}" 2>&1)"
rc=$?
echo "$out"
if [ "$rc" -ne 0 ]; then
  # Warn-only: a non-deterministic meter must not block an unrelated PR.
  echo "::warning title=Cost regression::per-run cost exceeded the rolling baseline (tolerance ${TOLERANCE})"
fi
exit 0
