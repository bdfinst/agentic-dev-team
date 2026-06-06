#!/usr/bin/env bash
# eval-changed.sh — run the paid live agent-eval, diff-scoped to what changed.
#
# Local mirror of the live-gate job in .github/workflows/agent-eval.yml:
#   1. Diff BASE..HEAD to find which agents/skills changed (a broad change to
#      knowledge/, the corpus, or the grader falls back to a full run, since one
#      knowledge file can feed many agents).
#   2. Dispatch the review agents headlessly via `claude -p /agent-eval`, scoped
#      to those targets, recording each agent's raw output to actuals.json.
#   3. Grade actuals.json against evals/baseline.json with the deterministic
#      grader, failing on any regression.
#
# This costs API tokens. The pre-push hook only calls it after you opt in.
#
# Usage:  bash scripts/eval-changed.sh BASE HEAD
# Exit:   0 = no regression (or nothing to eval), 1 = regression/failure.

set -uo pipefail

cd "$(git rev-parse --show-toplevel)" || exit 1

BASE="${1:-}"
HEAD="${2:-HEAD}"

if ! command -v claude >/dev/null 2>&1; then
  echo "eval-changed: 'claude' CLI not found on PATH — cannot run live evals." >&2
  exit 1
fi
if [ -z "${ANTHROPIC_API_KEY:-}" ] && [ -z "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
  echo "eval-changed: no ANTHROPIC_API_KEY/CLAUDE_CODE_OAUTH_TOKEN set; the" \
       "live eval needs credentials. Skipping." >&2
  exit 0
fi

# --- 1. diff-scope: which agents/skills changed? ---------------------------
SCOPE="full"
ONLY=""
if [ -n "$BASE" ]; then
  changed=$(git diff --name-only "$BASE" "$HEAD")
else
  # No base (e.g. brand-new branch): compare against the merge-base with main.
  mb=$(git merge-base HEAD origin/main 2>/dev/null || git merge-base HEAD main 2>/dev/null || true)
  if [ -n "$mb" ]; then
    changed=$(git diff --name-only "$mb" "$HEAD")
  else
    changed=$(git diff --name-only HEAD)
  fi
fi

# Broad changes feed many agents → full run. Mirrors the CI grep.
if echo "$changed" | grep -qE '^(plugins/dev-team/knowledge/|evals/|scripts/eval_grade\.py|\.github/workflows/agent-eval\.yml)'; then
  SCOPE="full"
else
  agents=$(echo "$changed" | sed -n 's#^plugins/dev-team/agents/\([^/]*\)\.md$#\1#p')
  skills=$(echo "$changed" | sed -n 's#^plugins/dev-team/skills/\([^/]*\)/.*#\1#p')
  ONLY=$(printf '%s\n%s\n' "$agents" "$skills" | sed '/^$/d' | sort -u | paste -sd, -)
  if [ -z "$ONLY" ]; then
    echo "eval-changed: no changed agents/skills detected — nothing to eval."
    exit 0
  fi
  SCOPE="scoped"
fi

if [ "$SCOPE" = "scoped" ]; then
  echo "eval-changed: diff-scoped run — only: $ONLY"
  INSTRUCTION="IMPORTANT: restrict this run to ONLY these agents/skills and skip all others: $ONLY"
else
  echo "eval-changed: broad change detected — full run."
  INSTRUCTION=""
fi

# --- 2. stage fixtures where the skill expects them ------------------------
# The agent-eval skill reads .claude/evals/{fixtures,expected}; the repo stores
# them under evals/. Symlink, exactly as CI does.
mkdir -p .claude/evals
ln -sfn "$PWD/evals/fixtures" .claude/evals/fixtures
ln -sfn "$PWD/evals/expected" .claude/evals/expected

# --- 3. record actuals.json via a headless Claude run ----------------------
rm -f actuals.json
PROMPT="Run the review agents against every fixture in
.claude/evals/fixtures/ whose paired .claude/evals/expected/<stem>.json
declares an applicableAgents (or applicableSkills) target, using the
/review-agent skill for agent fixtures and the test-design-advisor
skill for skill fixtures.

Do NOT grade. Record each agent's/skill's raw output and write it to
a file named actuals.json at the repository root, in EXACTLY this
shape (keyed by fixture stem — the expected filename without .json):

  {
    \"<stem>\": {
      \"agents\": {
        \"<agent>\": { \"status\": \"...\",
                     \"issues\": [{ \"severity\": \"...\", \"message\": \"...\" }],
                     \"summary\": \"...\" }
      },
      \"skills\": {
        \"<skill>\": { \"report\": \"full advisor report text\",
                     \"gates\": [\"A\"], \"layers\": [\"unit\"] }
      }
    }
  }

Include only the block(s) (agents/skills) that the fixture targets.
Write valid JSON and nothing else to actuals.json.

$INSTRUCTION"

echo "eval-changed: dispatching agents via claude -p (this costs tokens)…"
claude -p "$PROMPT" \
  --output-format json \
  --max-turns 60 \
  --model claude-sonnet-4-6 \
  --allowedTools "Read" "Glob" "Grep" "Write" "Agent" "Skill(review-agent *)" "Skill(test-design-advisor *)" \
  >/dev/null || true

if [ ! -f actuals.json ] || ! jq -e . actuals.json >/dev/null 2>&1; then
  echo "eval-changed: no parseable actuals.json was produced — the run did not" \
       "record results. Treating as skip (not a failure)." >&2
  exit 0
fi

# --- 4. grade against the baseline, diff-scoped ----------------------------
echo "eval-changed: grading against evals/baseline.json…"
python3 scripts/eval_grade.py \
  --actuals actuals.json \
  --baseline evals/baseline.json \
  --only "$ONLY"
