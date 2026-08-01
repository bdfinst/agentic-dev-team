#!/usr/bin/env bash
# run-ablation.sh — measure a knowledge file's retrieval value (#107).
#
# Runs the eval corpus WITH a knowledge file, then ABLATED (file hidden + index
# rebuilt), and diffs the grades via plugins/dev-team/scripts/eval_ablation.py
# (moved there in #1653 — its --find-latest mode ships with the plugin, this
# script's --mode knowledge invocation is still monorepo-only). Pairs that
# pass with the file but fail without it are its measured value.
#
# This costs API tokens (two corpus runs). Opt-in.
#
# Usage:  bash scripts/run-ablation.sh <knowledge-file.md> [--agent NAME]
# Exit:   0 ok, 2 missing prereq/arg.

set -uo pipefail
cd "$(git rev-parse --show-toplevel)" || exit 2

KFILE="${1:-}"
ONLY_AGENT=""
[ "${2:-}" = "--agent" ] && ONLY_AGENT="${3:-}"
KPATH="plugins/dev-team/knowledge/${KFILE}"
[ -n "$KFILE" ] && [ -f "$KPATH" ] || { echo "usage: run-ablation.sh <knowledge-file.md> [--agent NAME]" >&2; exit 2; }
for t in claude gh jq python3 git; do command -v "$t" >/dev/null 2>&1 || { echo "missing tool: $t" >&2; exit 2; }; done
[ -n "${ANTHROPIC_API_KEY:-}${CLAUDE_CODE_OAUTH_TOKEN:-}" ] || { echo "no API credentials set." >&2; exit 2; }

WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
INDEX="plugins/dev-team/hooks/lib/build-knowledge-index.sh"

mkdir -p .claude/evals
ln -sfn "$PWD/evals/fixtures" .claude/evals/fixtures
ln -sfn "$PWD/evals/expected" .claude/evals/expected

_dispatch() {  # _dispatch <out-actuals>
  local out="$1" extra=""
  [ -n "$ONLY_AGENT" ] && extra="Restrict the run to ONLY the agent '$ONLY_AGENT'."
  rm -f actuals.json
  claude -p "Run the review agents against every fixture in .claude/evals/fixtures/
whose paired .claude/evals/expected/<stem>.json declares applicableAgents, using
/review-agent. Pass each agent ONLY its fixture — never the expected status or a
severity example; let it decide every value. Do NOT grade. Write valid JSON only
to actuals.json keyed by fixture stem:
  { \"<stem>\": { \"agents\": { \"<agent>\": { \"status\": \"...\", \"issues\": [{ \"severity\": \"...\", \"message\": \"...\" }], \"summary\": \"...\" } } } }
$extra" \
    --output-format json --max-turns 200 --model claude-sonnet-4-6 \
    --allowedTools "Read" "Glob" "Grep" "Write" "Agent" "Skill(review-agent *)" \
    >/dev/null 2>&1 || true
  jq -e . actuals.json >/dev/null 2>&1 || { echo "no parseable actuals for $out" >&2; return 1; }
  mv actuals.json "$out"
}

echo "== baseline run (knowledge present) =="
_dispatch "$WORK/with.json" || exit 1

echo "== ablating $KFILE (hiding + rebuilding index) =="
mv "$KPATH" "$WORK/ablated.md"
bash "$INDEX" >/dev/null 2>&1 || true
# restore on any exit from here
trap 'mv "$WORK/ablated.md" "$KPATH" 2>/dev/null; bash "$INDEX" >/dev/null 2>&1; rm -rf "$WORK"' EXIT

echo "== ablated run (knowledge removed) =="
_dispatch "$WORK/without.json" || exit 1

echo "== restoring $KFILE =="
mv "$WORK/ablated.md" "$KPATH"; bash "$INDEX" >/dev/null 2>&1 || true
trap 'rm -rf "$WORK"' EXIT

echo "== retrieval value =="
ONLY_ARG=""; [ -n "$ONLY_AGENT" ] && ONLY_ARG="--only $ONLY_AGENT"
# shellcheck disable=SC2086
python3 plugins/dev-team/scripts/eval_ablation.py --expected-dir evals/expected \
  --baseline "$WORK/with.json" --ablated "$WORK/without.json" \
  --knowledge "$KFILE" $ONLY_ARG
