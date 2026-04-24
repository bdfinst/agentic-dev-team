#!/usr/bin/env bash
# Malformed mapping YAML -> hard-fail with the mapping path named.
set -u
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
ADAPTER="$REPO_ROOT/plugins/agentic-dev-team/skills/static-analysis-integration/adapters/security-review-adapter.py"
FXT_INPUT="$REPO_ROOT/evals/security-review-adapter/fixtures/agent-output-sql-injection.json"
BAD_MAP="$REPO_ROOT/evals/security-review-adapter/fixtures/malformed-mapping.yaml"
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT
# Copy bad map into tmp so we test --mapping invocation
TMP_MAP="$TMPDIR/bad.yaml"
cp "$BAD_MAP" "$TMP_MAP"
OUT="$TMPDIR/out.jsonl"
ERR="$TMPDIR/err.txt"

set +e
python3 "$ADAPTER" --input "$FXT_INPUT" --output "$OUT" --mapping "$TMP_MAP" 2>"$ERR"
rc=$?
set -e
if [[ $rc -ne 1 ]]; then
  echo "FAIL: expected exit 1, got $rc" >&2
  cat "$ERR" >&2
  exit 1
fi
if ! grep -qF "ERROR: mapping file at $TMP_MAP is invalid" "$ERR"; then
  echo "FAIL: stderr missing expected ERROR. Got:" >&2
  cat "$ERR" >&2
  exit 1
fi
echo "OK malformed mapping hard-fail"
