#!/usr/bin/env bash
# No uppercase letter appears in any emitted rule_id. AC-15.
set -u
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
ADAPTER="$REPO_ROOT/plugins/agentic-dev-team/skills/static-analysis-integration/adapters/security-review-adapter.py"
FXT="$REPO_ROOT/evals/security-review-adapter/fixtures/agent-output-mixed-case.json"
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT
OUT="$TMPDIR/out.jsonl"
python3 "$ADAPTER" --input "$FXT" --output "$OUT" >/dev/null
# Also test fallback path with an uppercase-internal A
FALL_INPUT="$TMPDIR/in-unmapped.json"
cat > "$FALL_INPUT" <<'JSON'
{"status":"warn","issues":[{"category":"A77.MIXED-class","severity":"warning","confidence":"medium","file":"x.py","line":1,"message":"m","suggestedFix":""}],"summary":""}
JSON
# A77.MIXED-class violates the regex (uppercase in slug). Category regex forbids that already.
# Use a valid-but-unmapped category that round-trips through lowercase():
cat > "$FALL_INPUT" <<'JSON'
{"status":"warn","issues":[{"category":"A77.mixed-class","severity":"warning","confidence":"medium","file":"x.py","line":1,"message":"m","suggestedFix":""}],"summary":""}
JSON
OUT2="$TMPDIR/out2.jsonl"
python3 "$ADAPTER" --input "$FALL_INPUT" --output "$OUT2" 2>/dev/null || true
# Scan emitted rule_ids for uppercase
if jq -r '.rule_id' "$OUT" "$OUT2" 2>/dev/null | grep -q '[A-Z]'; then
  echo "FAIL: uppercase letter found in emitted rule_id" >&2
  jq -r '.rule_id' "$OUT" "$OUT2" >&2
  exit 1
fi
echo "OK case normalization"
