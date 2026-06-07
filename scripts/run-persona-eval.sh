#!/usr/bin/env bash
# run-persona-eval.sh — persona ON vs OFF for one agent (#110).
#
# Runs the corpus with an agent's persona prose present, then with it stripped,
# multi-trial, and diffs pass@k via scripts/eval_persona.py. A delta only counts
# when it clears the variance band (neither run flapped).
#
# GUARD (the experiment's validity hinges on this): the OFF variant MUST differ
# from the ON definition. If stripping the persona changed nothing, the run is
# meaningless and this aborts — exactly the failure mode the verification plan
# warns about.
#
# Persona prose is taken to be a leading `## Persona` / `## Identity` / `## Role`
# section in the agent .md (everything from that header to the next `## `). Agents
# without such a section can't be toggled automatically — supply an OFF variant.
#
# Usage:  bash scripts/run-persona-eval.sh <agent-name> [TRIALS]
# Exit:   0 ok, 2 missing prereq/arg, 3 toggle did not change the agent.

set -uo pipefail
cd "$(git rev-parse --show-toplevel)" || exit 2

AGENT="${1:-}"; TRIALS="${2:-3}"
APATH="plugins/dev-team/agents/${AGENT}.md"
[ -n "$AGENT" ] && [ -f "$APATH" ] || { echo "usage: run-persona-eval.sh <agent-name> [TRIALS]" >&2; exit 2; }
for t in claude gh jq python3 git; do command -v "$t" >/dev/null 2>&1 || { echo "missing tool: $t" >&2; exit 2; }; done
[ -n "${ANTHROPIC_API_KEY:-}${CLAUDE_CODE_OAUTH_TOKEN:-}" ] || { echo "no API credentials set." >&2; exit 2; }

WORK="$(mktemp -d)"; trap 'mv "$WORK/agent-on.md" "$APATH" 2>/dev/null; rm -rf "$WORK"' EXIT
mkdir -p "$WORK/on" "$WORK/off"
cp "$APATH" "$WORK/agent-on.md"

# Build the persona-OFF variant: drop a leading Persona/Identity/Role section.
python3 - "$APATH" "$WORK/agent-off.md" <<'PY'
import re, sys
src = open(sys.argv[1]).read()
out = re.sub(r"\n##\s+(Persona|Identity|Role)\b.*?(?=\n##\s|\Z)", "\n", src,
             flags=re.IGNORECASE | re.DOTALL)
open(sys.argv[2], "w").write(out)
PY

# GUARD: the toggle must have changed something.
if diff -q "$WORK/agent-on.md" "$WORK/agent-off.md" >/dev/null; then
  echo "toggle did NOT change ${AGENT} — no Persona/Identity/Role section to strip." >&2
  echo "Supply an OFF variant manually; aborting (a no-op toggle measures nothing)." >&2
  exit 3
fi
echo "toggle verified: persona-OFF differs from persona-ON ($(diff "$WORK/agent-on.md" "$WORK/agent-off.md" | grep -c '^<') lines removed)."

mkdir -p .claude/evals
ln -sfn "$PWD/evals/fixtures" .claude/evals/fixtures
ln -sfn "$PWD/evals/expected" .claude/evals/expected

_dispatch() {  # _dispatch <out>
  rm -f actuals.json
  claude -p "Run the '$AGENT' review agent against every fixture in
.claude/evals/fixtures/ whose paired expected json targets it, via /review-agent.
Pass the agent ONLY its fixture — never the expected status or a severity example.
Do NOT grade. Write valid JSON only to actuals.json keyed by fixture stem:
  { \"<stem>\": { \"agents\": { \"$AGENT\": { \"status\": \"...\", \"issues\": [{ \"severity\": \"...\", \"message\": \"...\" }], \"summary\": \"...\" } } } }" \
    --output-format json --max-turns 120 --model claude-sonnet-4-6 \
    --allowedTools "Read" "Glob" "Grep" "Write" "Agent" "Skill(review-agent *)" \
    >/dev/null 2>&1 || true
  jq -e . actuals.json >/dev/null 2>&1 && mv actuals.json "$1"
}

echo "== persona ON ($TRIALS trials) =="
cp "$WORK/agent-on.md" "$APATH"
for n in $(seq 1 "$TRIALS"); do _dispatch "$WORK/on/t$n.json"; done

echo "== persona OFF ($TRIALS trials) =="
cp "$WORK/agent-off.md" "$APATH"
for n in $(seq 1 "$TRIALS"); do _dispatch "$WORK/off/t$n.json"; done
cp "$WORK/agent-on.md" "$APATH"   # restore

echo "== persona delta =="
python3 scripts/eval_persona.py --on-trials "$WORK/on" --off-trials "$WORK/off" \
  --expected-dir evals/expected
