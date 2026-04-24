#!/usr/bin/env bash
# Well-formed-but-unmapped category -> fallback rule_id + WARN. AC-7.
set -u
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
ADAPTER="$REPO_ROOT/plugins/agentic-dev-team/skills/static-analysis-integration/adapters/security-review-adapter.py"
FXT="$REPO_ROOT/evals/security-review-adapter/fixtures/agent-output-unmapped-category.json"
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT
OUT="$TMPDIR/out.jsonl"
ERR="$TMPDIR/err.txt"

set +e
# cd to repo root so the adapter reports the repo-relative mapping path
(cd "$REPO_ROOT" && python3 "$ADAPTER" --input "$FXT" --output "$OUT" \
  --mapping plugins/agentic-dev-team/knowledge/security-review-rule-map.yaml 2>"$ERR")
rc=$?
set -e
if [[ $rc -ne 0 ]]; then
  echo "FAIL: expected exit 0, got $rc" >&2
  cat "$ERR" >&2
  exit 1
fi
got_rule=$(jq -r '.rule_id' "$OUT" | head -1)
if [[ "$got_rule" != "security-review.a99.new-class" ]]; then
  echo "FAIL: wrong rule_id $got_rule" >&2
  exit 1
fi
expected="WARN: category A99.new-class not in mapping at plugins/agentic-dev-team/knowledge/security-review-rule-map.yaml; minted security-review.a99.new-class"
if ! grep -qF "$expected" "$ERR"; then
  echo "FAIL: stderr missing expected WARN. Got:" >&2
  cat "$ERR" >&2
  echo "Expected fragment: $expected" >&2
  exit 1
fi
echo "OK unmapped category fallback"
