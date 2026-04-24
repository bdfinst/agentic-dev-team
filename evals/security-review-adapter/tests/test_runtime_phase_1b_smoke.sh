#!/usr/bin/env bash
# Runtime Phase 1b smoke test: execute the documented invocation from
# security-assessment-pipeline/SKILL.md against a staged fixture. AC-10.
set -u
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
ADAPTER="$REPO_ROOT/plugins/agentic-dev-team/skills/static-analysis-integration/adapters/security-review-adapter.py"
FXT="$REPO_ROOT/evals/security-review-adapter/fixtures/agent-output-phase-1b-smoke.json"
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

mkdir -p "$TMPDIR/memory"
cp "$FXT" "$TMPDIR/memory/agent-output.json"

# Simulate the Phase 1b invocation verbatim (see security-assessment-pipeline/SKILL.md).
(cd "$TMPDIR" && python3 "$ADAPTER" \
  --input memory/agent-output.json \
  --output memory/findings-fxt.jsonl \
  2>/dev/null) || {
  # A WARN on the unmapped category is expected (exits 0).
  true
}

OUT="$TMPDIR/memory/findings-fxt.jsonl"
if [[ ! -s "$OUT" ]]; then
  echo "FAIL: memory/findings-fxt.jsonl missing or empty" >&2
  exit 1
fi
lines=$(wc -l < "$OUT" | tr -d ' ')
if [[ "$lines" != "2" ]]; then
  echo "FAIL: expected 2 lines, got $lines" >&2
  cat "$OUT" >&2
  exit 1
fi

while read -r line; do
  rule=$(echo "$line" | jq -r '.rule_id')
  src=$(echo "$line" | jq -r '.metadata.source')
  if [[ -z "$rule" || "$rule" == "null" ]]; then
    echo "FAIL: empty rule_id on line: $line" >&2; exit 1
  fi
  if [[ "$src" != "security-review" ]]; then
    echo "FAIL: metadata.source != security-review: $src" >&2; exit 1
  fi
done < "$OUT"

echo "OK runtime phase 1b smoke"
