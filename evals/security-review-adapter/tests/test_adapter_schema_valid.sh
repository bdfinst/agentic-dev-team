#!/usr/bin/env bash
# Every positive-fixture emitted line validates against unified-finding-v1.json. AC-4.
set -u
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
ADAPTER="$REPO_ROOT/plugins/agentic-dev-team/skills/static-analysis-integration/adapters/security-review-adapter.py"
SCHEMA="$REPO_ROOT/plugins/agentic-dev-team/knowledge/schemas/unified-finding-v1.json"
FXT="$REPO_ROOT/evals/security-review-adapter/fixtures"
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

rc=0
for input in "$FXT/agent-output-sql-injection.json" "$FXT/agent-output-xss-innerhtml.json" "$FXT/agent-output-idor.json" "$FXT/agent-output-mixed-case.json"; do
  out="$TMPDIR/$(basename "$input" .json).jsonl"
  python3 "$ADAPTER" --input "$input" --output "$out" || { echo "FAIL: adapter nonzero on $input" >&2; rc=1; continue; }
  python3 - "$out" "$SCHEMA" <<'PY'
import json, sys
from jsonschema import Draft202012Validator
schema = json.load(open(sys.argv[2]))
validator = Draft202012Validator(schema)
failed = False
with open(sys.argv[1]) as fh:
    for i, line in enumerate(fh, 1):
        if not line.strip():
            continue
        obj = json.loads(line)
        errors = sorted(validator.iter_errors(obj), key=lambda e: e.path)
        if errors:
            for e in errors:
                print(f"FAIL line {i}: {e.message} at {list(e.path)}", file=sys.stderr)
            failed = True
sys.exit(1 if failed else 0)
PY
  [[ $? -eq 0 ]] || { echo "FAIL schema validation: $input" >&2; rc=1; }
done
[[ $rc -eq 0 ]] && echo "OK schema valid"
exit $rc
