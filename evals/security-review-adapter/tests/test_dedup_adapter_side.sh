#!/usr/bin/env bash
# Adapter-side dedup: agent finding at api.py:42 with category A03.sql-injection
# and semgrep finding at same location+rule_id collapse to one unified finding
# under fp-reduction's documented dedup key. AC-9.
#
# End-to-end Phase 1b dedup is tested by test_runtime_phase_1b_smoke in Step 6.
set -u
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
ADAPTER="$REPO_ROOT/plugins/agentic-dev-team/skills/static-analysis-integration/adapters/security-review-adapter.py"
FXT="$REPO_ROOT/evals/security-review-adapter/fixtures"
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

AGENT_OUT="$TMPDIR/agent-unified.jsonl"
python3 "$ADAPTER" --input "$FXT/dedup-agent-output.json" --output "$AGENT_OUT" \
  || { echo "FAIL: adapter nonzero" >&2; exit 1; }

# Assert agent emitted rule_id matches semgrep's (upstream-aligned).
got_rule=$(jq -r '.rule_id' "$AGENT_OUT")
if [[ "$got_rule" != "semgrep.generic.sql-injection" ]]; then
  echo "FAIL: agent rule_id $got_rule != semgrep.generic.sql-injection" >&2
  exit 1
fi

# Concatenate both and apply fp-reduction's documented dedup key.
# SOURCE: plugins/agentic-security-review/skills/false-positive-reduction/SKILL.md
# (Stage 4 Dedup): "Same rule_id + same value across multiple files -> collapse to ONE"
# For same-file same-line same-rule_id, dedup key is (rule_id, file, line).
COMBINED="$TMPDIR/combined.jsonl"
cat "$FXT/dedup-semgrep.jsonl" "$AGENT_OUT" > "$COMBINED"

python3 - "$COMBINED" <<'PY'
import json, sys
seen = {}
with open(sys.argv[1]) as fh:
    for line in fh:
        if not line.strip(): continue
        o = json.loads(line)
        key = (o["rule_id"], o["file"], o["line"])
        # keep first-seen (semgrep first by cat order, mirroring priority)
        if key not in seen:
            seen[key] = o
if len(seen) != 1:
    print(f"FAIL: expected 1 post-dedup finding, got {len(seen)}", file=sys.stderr)
    for k, v in seen.items():
        print(f"  {k}: {v}", file=sys.stderr)
    sys.exit(1)
survivor = next(iter(seen.values()))
if survivor["rule_id"] != "semgrep.generic.sql-injection":
    print(f"FAIL: surviving rule_id {survivor['rule_id']}", file=sys.stderr); sys.exit(1)
print("OK adapter-side dedup collapse")
PY
