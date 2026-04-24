#!/usr/bin/env bash
# Malformed category (regex-violating) must be a hard-fail. AC-16.
set -u
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
ADAPTER="$REPO_ROOT/plugins/agentic-dev-team/skills/static-analysis-integration/adapters/security-review-adapter.py"
FXT="$REPO_ROOT/evals/security-review-adapter/fixtures/agent-output-malformed-category.json"
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT
OUT="$TMPDIR/out.jsonl"
ERR="$TMPDIR/err.txt"

set +e
python3 "$ADAPTER" --input "$FXT" --output "$OUT" 2>"$ERR"
rc=$?
set -e
if [[ $rc -ne 1 ]]; then
  echo "FAIL: expected exit 1, got $rc" >&2
  cat "$ERR" >&2
  exit 1
fi
if ! grep -qF "ERROR: category 'A3.sqli' does not match required format A<NN>.<slug>" "$ERR"; then
  echo "FAIL: stderr missing expected ERROR line. Got:" >&2
  cat "$ERR" >&2
  exit 1
fi
if [[ -s "$OUT" ]]; then
  echo "FAIL: output file is non-empty on malformed category" >&2
  cat "$OUT" >&2
  exit 1
fi
echo "OK malformed category hard-fail"
