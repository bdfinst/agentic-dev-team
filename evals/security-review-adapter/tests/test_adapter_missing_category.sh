#!/usr/bin/env bash
# Missing category field -> hard-fail. AC-8.
set -u
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
ADAPTER="$REPO_ROOT/plugins/agentic-dev-team/skills/static-analysis-integration/adapters/security-review-adapter.py"
FXT="$REPO_ROOT/evals/security-review-adapter/fixtures/agent-output-missing-category.json"
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
if ! grep -qF "ERROR: agent issue missing required 'category' field; upgrade the agent output" "$ERR"; then
  echo "FAIL: stderr missing expected ERROR. Got:" >&2
  cat "$ERR" >&2
  exit 1
fi
echo "OK missing category hard-fail"
