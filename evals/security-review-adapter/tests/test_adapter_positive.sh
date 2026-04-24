#!/usr/bin/env bash
# Positive adapter runs: three mapped fixtures, deep-equal expected, source_ref byte-faithful.
# Closes AC-3, AC-5, AC-6, AC-17 (partially), AC-4 (via positive schema fixture covered in Step 3).
set -u
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
ADAPTER="$REPO_ROOT/plugins/agentic-dev-team/skills/static-analysis-integration/adapters/security-review-adapter.py"
FXT="$REPO_ROOT/evals/security-review-adapter/fixtures"
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

if [[ ! -f "$ADAPTER" ]]; then
  echo "FAIL: adapter missing at $ADAPTER" >&2
  exit 1
fi

run_case() {
  local input="$1"
  local expected="$2"
  local tmp="$TMPDIR/$(basename "$input" .json).jsonl"
  python3 "$ADAPTER" --input "$input" --output "$tmp" || { echo "FAIL: adapter nonzero on $input" >&2; return 1; }
  # Deep-equal emitted vs expected (JSON-aware compare, tolerant to whitespace)
  python3 - "$tmp" "$expected" <<'PY'
import json, sys
with open(sys.argv[1]) as fh:
    emitted = [json.loads(l) for l in fh if l.strip()]
with open(sys.argv[2]) as fh:
    expected = [json.loads(l) for l in fh if l.strip()]
if emitted != expected:
    import pprint
    print("FAIL: emitted != expected", file=sys.stderr)
    print("emitted:", json.dumps(emitted, indent=2, sort_keys=True), file=sys.stderr)
    print("expected:", json.dumps(expected, indent=2, sort_keys=True), file=sys.stderr)
    sys.exit(1)
PY
  [[ $? -eq 0 ]] || return 1
  # Byte-faithful source_ref: jq .metadata.source_ref of line 1 == jq .issues[0] of input
  local src_ref
  local input_issue
  src_ref=$(jq -c -S '.metadata.source_ref' "$tmp" | head -n1)
  input_issue=$(jq -c -S '.issues[0]' "$input")
  if [[ "$src_ref" != "$input_issue" ]]; then
    echo "FAIL: source_ref not byte-faithful for $input" >&2
    echo "got: $src_ref" >&2
    echo "want: $input_issue" >&2
    return 1
  fi
  return 0
}

rc=0
run_case "$FXT/agent-output-sql-injection.json" "$FXT/expected-unified-sql-injection.jsonl" || rc=1
run_case "$FXT/agent-output-xss-innerhtml.json" "$FXT/expected-unified-xss-innerhtml.jsonl" || rc=1
run_case "$FXT/agent-output-idor.json" "$FXT/expected-unified-idor.jsonl" || rc=1

if [[ $rc -eq 0 ]]; then
  echo "OK adapter positive"
fi
exit $rc
