#!/usr/bin/env bash
# run-rawlog-tier.sh — raw-log semantic tier over the worst sessions (#180).
#
# 1. Flag the top-N worst sessions from the digests (scripts/eval_rawlog.py).
# 2. For each, dispatch ONE agent to read that raw transcript and report semantic
#    frictions (e.g. hallucinated citations) plus a `methodology` lens — output
#    held to metrics-only/no-quote.
# 3. Validate every finding through the privacy guard; drop any that leak.
#
# Only the worst sessions get the (expensive) raw pass — the rest are never read.
# Costs API tokens. Opt-in.
#
# Usage:  bash scripts/run-rawlog-tier.sh [DIGESTS_DIR] [--top N]
# Exit:   0 ok, 2 missing prereq.

set -uo pipefail
cd "$(git rev-parse --show-toplevel)" || exit 2

DIGESTS="${1:-${DEV_TEAM_TELEMETRY_CLONE:-$HOME/.claude/.dev-team/agent-telemetry}/digests}"
TOP=5
[ "${2:-}" = "--top" ] && TOP="${3:-5}"
PROJECTS="$HOME/.claude/projects"
for t in claude jq python3 git; do command -v "$t" >/dev/null 2>&1 || { echo "missing tool: $t" >&2; exit 2; }; done
[ -n "${ANTHROPIC_API_KEY:-}${CLAUDE_CODE_OAUTH_TOKEN:-}" ] || { echo "no API credentials set." >&2; exit 2; }
[ -d "$DIGESTS" ] || { echo "no digests dir at $DIGESTS" >&2; exit 2; }

WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT

echo "== flagging worst $TOP sessions =="
python3 scripts/eval_rawlog.py --flag "$DIGESTS" --top "$TOP" -o "$WORK/flagged.json"
mapfile -t SIDS < <(jq -r '.worst_sessions[].session_id' "$WORK/flagged.json")
[ "${#SIDS[@]}" -gt 0 ] || { echo "no sessions to review."; exit 0; }

echo "[]" > "$WORK/findings.json"
for sid in "${SIDS[@]}"; do
  tx="$(find "$PROJECTS" -name "${sid}.jsonl" 2>/dev/null | head -1)"
  [ -n "$tx" ] || { echo "  $sid: transcript not found, skipping" >&2; continue; }
  echo "== raw-log review: $sid =="
  rm -f rawlog-out.json
  claude -p "Read the Claude Code session transcript at '$tx' and identify SEMANTIC
frictions a metrics digest cannot see: hallucinated citations (the model citing a
skill/file as a source when that content does not exist), the AI repeating a
mistake that slipped a guardrail, and OPERATOR methodology habits (e.g. deferring
decisions with no owner). Also note dev-environment papercuts.

OUTPUT DISCIPLINE — this is mandatory: write a JSON array to rawlog-out.json. Each
finding may contain ONLY these keys: session_id, project, host, friction_type,
lens (one of: methodology, harness, devex, accuracy), target_artifact, confidence,
count. NEVER include a quote, snippet, code, file path, or any prompt/output text.
Report THAT a friction occurred and WHICH artifact to fix — never the content.
session_id is '$sid'. Write valid JSON only." \
    --output-format json --max-turns 30 --model claude-sonnet-4-6 \
    --allowedTools "Read" "Write" >/dev/null 2>&1 || true
  if jq -e 'type=="array"' rawlog-out.json >/dev/null 2>&1; then
    jq -s '.[0] + .[1]' "$WORK/findings.json" rawlog-out.json > "$WORK/m.json" && mv "$WORK/m.json" "$WORK/findings.json"
  fi
  rm -f rawlog-out.json
done

echo "== privacy validation (drop any leaking finding) =="
python3 scripts/eval_rawlog.py --validate "$WORK/findings.json" -o "$WORK/validation.json"
if [ "$(jq -r '.ok' "$WORK/validation.json")" != "true" ]; then
  echo "WARNING: some findings violated the metrics-only boundary and are reported below; do NOT ship them:" >&2
  jq '.violations' "$WORK/validation.json" >&2
fi
echo "== clean findings =="
jq --slurpfile v "$WORK/validation.json" \
   'to_entries | map(select((($v[0].violations // []) | map(.index) | index(.key)) | not) | .value)' \
   "$WORK/findings.json"
