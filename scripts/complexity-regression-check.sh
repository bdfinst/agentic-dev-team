#!/usr/bin/env bash
# Complexity regression check for AC2 of epic #362 (issue #366).
#
# Measures mean complexity-review findings/solution on the 6 Campaign B tasks
# run test-first with the current plugin. Compares against the pre-P1-S1 baseline
# (5.3 findings/solution) documented in docs/experiments/agentic-workflow-evidence/data/3sizes-3arms-summary.json.
#
# Usage:
#   bash scripts/complexity-regression-check.sh [--model <model-id>]
#
# Requires: jq, python3, a plugin-enabled HOME template (--build-home-template).
# Approx. cost: ~$2 (6 tasks × 1 trial × test-first arm only).
# Approx. time: 15-30 minutes.
#
# Output: docs/experiments/agentic-workflow-evidence/data/complexity-regression-<date>.json
#         Exit 0 if mean findings < baseline; exit 1 if findings >= baseline.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BASELINE=5.3
MODEL="${MODEL:-claude-sonnet-4-6}"
OUT_DIR="$REPO_ROOT/docs/experiments/data"
DATE="$(date +%Y-%m-%d)"
OUT_FILE="$OUT_DIR/complexity-regression-$DATE.json"

TASKS=(stats intervals timeparse money matrix csvlite)

usage() {
  echo "Usage: $0 [--model <model-id>] [--out <path>]"
  echo ""
  echo "Measures complexity-review findings on test-first solutions for the"
  echo "6 Campaign B tasks and compares against the pre-P1-S1 baseline (${BASELINE})."
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --model) MODEL="$2"; shift 2 ;;
    --out)   OUT_FILE="$2"; shift 2 ;;
    --help|-h) usage ;;
    *) echo "Unknown argument: $1"; usage ;;
  esac
done

echo "=== Complexity Regression Check (AC2, epic #362) ==="
echo "Baseline: ${BASELINE} findings/solution (pre-P1-S1, test-first arm)"
echo "Model: $MODEL"
echo "Output: $OUT_FILE"
echo ""
echo "This runs the test-first arm for each of the 6 Campaign B tasks,"
echo "then dispatches complexity-review on the produced solution."
echo ""
echo "Step 1: Run test-first experiment arm (6 tasks × 1 trial)"
python3 "$SCRIPT_DIR/run_tdd_experiment.py" \
  --arm test-first \
  --only "${TASKS[@]/#/exp-tdd-}" \
  --trials 1 \
  --model "$MODEL" \
  --emit-complexity-findings \
  --out "$OUT_DIR/complexity-regression-raw-$DATE.jsonl"

echo ""
echo "Step 2: Aggregate findings"
python3 - <<'PYEOF'
import json, sys, math
from pathlib import Path

raw = Path(f"docs/experiments/agentic-workflow-evidence/data/complexity-regression-raw-{sys.argv[1]}.jsonl")
if not raw.exists():
    print(f"ERROR: {raw} not found — did the experiment run complete?", file=sys.stderr)
    sys.exit(1)

records = [json.loads(l) for l in raw.read_text().splitlines() if l.strip()]
build_records = [r for r in records if r.get("stage") == "build" and r.get("arm") == "test-first"]

findings = {r["task"].replace("exp-tdd-", ""): r.get("complexity_findings", 0) for r in build_records}
mean = sum(findings.values()) / len(findings) if findings else 0

result = {
    "date": sys.argv[1],
    "arm": "test-first",
    "baseline_mean": 5.3,
    "measured_mean": round(mean, 1),
    "delta": round(mean - 5.3, 1),
    "ac2_pass": mean < 5.3,
    "per_task": findings
}
print(json.dumps(result, indent=2))
PYEOF

echo ""
if python3 -c "
import json, sys
from pathlib import Path

raw_date = '$DATE'
raw = Path(f'docs/experiments/agentic-workflow-evidence/data/complexity-regression-raw-{raw_date}.jsonl')
if not raw.exists():
    sys.exit(1)
records = [json.loads(l) for l in raw.read_text().splitlines() if l.strip()]
build_records = [r for r in records if r.get('stage') == 'build' and r.get('arm') == 'test-first']
findings = [r.get('complexity_findings', 0) for r in build_records]
mean = sum(findings) / len(findings) if findings else 9999
sys.exit(0 if mean < $BASELINE else 1)
" 2>/dev/null; then
  echo "PASS: mean findings < baseline (${BASELINE}). AC2 satisfied."
  exit 0
else
  echo "FAIL: mean findings >= baseline (${BASELINE}). REFACTOR review is not reducing complexity."
  exit 1
fi
