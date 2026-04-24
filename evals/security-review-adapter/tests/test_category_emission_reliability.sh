#!/usr/bin/env bash
# Reliability eval: for each canned case, check the (simulated) agent emission
# matches the expected category. Floor: >=80% accuracy. Step 4 reliability eval.
# Real-agent accuracy is a post-merge follow-up (R7).
set -u
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
DIR="$REPO_ROOT/evals/security-review-adapter/fixtures/reliability"

python3 - "$DIR" <<'PY'
import json, pathlib, sys
d = pathlib.Path(sys.argv[1])
cases = sorted(d.glob("case-*.json"))
if len(cases) < 3:
    print(f"FAIL: need >=3 cases, got {len(cases)}", file=sys.stderr); sys.exit(1)
pass_count = 0
failures = []
for c in cases:
    obj = json.loads(c.read_text())
    expected = obj["expected_category"]
    # Canned agent output for CI determinism. Real-agent mode lives in a follow-up.
    emitted = obj["agent_output"]["issues"][0].get("category", "")
    if emitted == expected:
        pass_count += 1
    else:
        failures.append((c.name, expected, emitted))
total = len(cases)
accuracy = pass_count / total
print(f"cases={total} pass={pass_count} accuracy={accuracy:.2%}")
for name, expected, emitted in failures:
    print(f"  FAIL: {name} expected={expected} emitted={emitted}", file=sys.stderr)
if accuracy < 0.80:
    print("FAIL: accuracy below 80% floor", file=sys.stderr)
    sys.exit(1)
print("OK reliability eval (canned agent output)")
PY
