#!/usr/bin/env bash
# run-full-eval.sh — run the agent-eval corpus, refresh the tracked eval data,
# and open an auto-merge PR. Supports full, single-agent, and a RESUMABLE sweep.
#
# Modes:
#   (default)        RESUMABLE SWEEP: every agent, one at a time, checkpointed. If
#                    you kill it or run out of tokens, just re-run and it picks up
#                    where it left off (per-agent commits + a checkpoint file are
#                    the progress). One auto-merge PR at the end.
#   --agent NAME     just that agent (incremental; merges its pairs, others kept).
#
# This costs API tokens. Default TRIALS=1.
#
# Usage:  bash scripts/run-full-eval.sh [TRIALS] [--agent NAME]
#         (no flag = resumable full sweep; --sweep accepted as the default alias)
# Env:    ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN, plus `claude` + `gh`.
# Exit:   0 ok, 2 missing prereq, 1 run produced nothing.

set -uo pipefail
cd "$(git rev-parse --show-toplevel)" || exit 2

# The RESUMABLE SWEEP is the default. --agent NAME scopes to a single agent
# instead; --sweep is accepted as a (now-default) alias for back-compat.
TRIALS=1; ONLY_AGENT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --agent) ONLY_AGENT="${2:-}"; shift 2 ;;
    --sweep) shift ;;                 # default behavior; kept for back-compat
    [0-9]*)  TRIALS="$1"; shift ;;
    *) echo "usage: run-full-eval.sh [TRIALS] [--agent NAME]   (default: resumable full sweep)" >&2; exit 2 ;;
  esac
done
STAMP="$(date -u +%Y%m%d-%H%M%S)"
CKPT=".eval-sweep-progress.json"   # gitignored; the resume handle

# --- prerequisites ----------------------------------------------------------
for t in claude gh jq python3 git; do
  command -v "$t" >/dev/null 2>&1 || { echo "missing required tool: $t" >&2; exit 2; }
done
if [ -z "${ANTHROPIC_API_KEY:-}" ] && [ -z "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
  echo "no ANTHROPIC_API_KEY / CLAUDE_CODE_OAUTH_TOKEN — the live eval needs creds." >&2
  exit 2
fi

# --- stage fixtures where the skill expects them (mirrors eval-changed.sh) ---
mkdir -p .claude/evals
ln -sfn "$PWD/evals/fixtures" .claude/evals/fixtures
ln -sfn "$PWD/evals/expected" .claude/evals/expected

read -r -d '' PROMPT_BASE <<'EOF'
Run the review agents against the fixtures in .claude/evals/fixtures/ whose paired
.claude/evals/expected/<stem>.json declares an applicableAgents target, via the
/review-agent skill.

CRITICAL — do NOT bias the agents: pass each agent ONLY its fixture file. Do not
tell it the expected status or severity. Let it decide every value itself.

Do NOT grade. Write valid JSON (and nothing else) to actuals.json at the repo
root, keyed by fixture stem:

  { "<stem>": { "agents": { "<agent>": { "status": "...",
        "issues": [{ "severity": "...", "message": "..." }], "summary": "..." } } } }
EOF

# _dispatch <scope-instruction> <trials-dir> -> prints the number of good trials
_dispatch() {
  local instr="$1" tdir="$2" prompt="$PROMPT_BASE" n cnt=0
  [ -n "$instr" ] && prompt="${prompt}"$'\n\n'"${instr}"
  for n in $(seq 1 "$TRIALS"); do
    rm -f actuals.json
    claude -p "$prompt" --output-format json --max-turns 200 --model claude-sonnet-4-6 \
      --allowedTools "Read" "Glob" "Grep" "Write" "Agent" \
                     "Skill(review-agent *)" "Skill(test-design-advisor *)" \
      >/dev/null 2>&1 || true
    if jq -e . actuals.json >/dev/null 2>&1; then cp actuals.json "$tdir/trial-${n}.json"; cnt=$((cnt + 1)); fi
  done
  rm -f actuals.json
  echo "$cnt"
}

# _grade_variance <agent-or-empty> <trials-dir> — update baseline.json in the
# tree (merged; --only when scoped) and append the variance trend.
_grade_variance() {
  local agent="$1" tdir="$2" ft only=() ve="evals/expected"
  ft="$(find "$tdir" -name 'trial-*.json' | sort | head -1)"
  [ -n "$agent" ] && only=(--only "$agent")
  python3 scripts/eval_grade.py --actuals "$ft" "${only[@]}" \
    --write-baseline evals/baseline.json || true
  if [ "$(find "$tdir" -name 'trial-*.json' | wc -l)" -gt 1 ]; then
    if [ -n "$agent" ]; then
      ve="$tdir/expected"; mkdir -p "$ve"
      for ef in evals/expected/*.json; do
        jq -e --arg a "$agent" '.applicableAgents // [] | index($a)' "$ef" >/dev/null 2>&1 && cp "$ef" "$ve/"
      done
    fi
    python3 scripts/eval_variance.py --trials-dir "$tdir" --expected-dir "$ve" \
      --append metrics/eval-variance.jsonl -o memory/eval-variance.json >/dev/null || true
  fi
}

# ===================== RESUMABLE SWEEP (default mode) ======================
if [ -z "$ONLY_AGENT" ]; then
  if [ -f "$CKPT" ]; then
    BRANCH="$(jq -r .branch "$CKPT")"; TRIALS="$(jq -r .trials "$CKPT")"
    echo "resuming sweep on '$BRANCH' — $(jq -r '.done | length' "$CKPT") agent(s) already done."
    git checkout "$BRANCH" >/dev/null 2>&1 || { echo "cannot checkout sweep branch $BRANCH" >&2; exit 2; }
    git checkout -- evals/baseline.json 2>/dev/null || true   # drop any partial from an interrupted agent
  else
    if ! git diff --quiet || ! git diff --cached --quiet; then echo "working tree is dirty — commit or stash first." >&2; exit 2; fi
    BRANCH="eval/sweep-${STAMP}"
    git checkout -b "$BRANCH" >/dev/null 2>&1 || { echo "branch create failed" >&2; exit 2; }
    jq -n --arg b "$BRANCH" --argjson t "$TRIALS" '{branch:$b, trials:$t, done:[]}' > "$CKPT"
    echo "started sweep on '$BRANCH'."
  fi

  mapfile -t ALL_AGENTS < <(jq -r '.applicableAgents[]?' evals/expected/*.json 2>/dev/null | sort -u)
  for agent in "${ALL_AGENTS[@]}"; do
    if jq -e --arg a "$agent" '.done | index($a)' "$CKPT" >/dev/null 2>&1; then
      echo "skip (done): $agent"; continue
    fi
    echo "== agent: $agent ($TRIALS trial(s)) — dispatching =="
    tdir="$(mktemp -d)"
    cnt="$(_dispatch "IMPORTANT: restrict this run to ONLY the agent '${agent}' and the fixtures that target it; skip every other agent and skill." "$tdir")"
    if [ "$cnt" -eq 0 ]; then
      echo "  no actuals for $agent — leaving un-done; re-run to retry." >&2; rm -rf "$tdir"; continue
    fi
    _grade_variance "$agent" "$tdir"; rm -rf "$tdir"
    # checkpoint: commit the baseline delta (progress lives in git) + mark done
    if ! git diff --quiet -- evals/baseline.json; then
      git add evals/baseline.json
      git commit -q -m "test(evals): sweep baseline for ${agent} (${STAMP})"
    fi
    tmp="$(mktemp)"; jq --arg a "$agent" '.done += [$a]' "$CKPT" > "$tmp" && mv "$tmp" "$CKPT"
    echo "  done: $agent ($(jq -r '.done | length' "$CKPT")/${#ALL_AGENTS[@]})"
  done

  echo "== sweep complete: $(jq -r '.done | length' "$CKPT")/${#ALL_AGENTS[@]} agents =="
  if [ -n "$(git log origin/main..HEAD --oneline 2>/dev/null)" ]; then
    git push -u origin "$BRANCH" >/dev/null 2>&1 || { echo "push failed" >&2; exit 2; }
    PR_URL="$(gh pr create --title "test(evals): full sweep baseline refresh (${STAMP})" \
      --body "Resumable full-corpus sweep via \`run-full-eval.sh --sweep\` — every agent, one per commit.

Merges per-agent results into \`evals/baseline.json\`. Review the diff for **regressions** (pairs dropped) or **improvements** (pairs newly passing). Variance appended to the local trend." 2>/dev/null)"
    echo "opened: $PR_URL"
    gh pr merge "$(echo "$PR_URL" | grep -oE '[0-9]+$')" --auto --squash --delete-branch >/dev/null 2>&1 \
      && echo "auto-merge enabled" || echo "could not enable auto-merge (enable manually)"
  else
    echo "no baseline changes across the sweep — no PR."
  fi
  rm -f "$CKPT"
  exit 0
fi

# ==================== SINGLE-AGENT RUN (--agent NAME) ======================
if ! git diff --quiet || ! git diff --cached --quiet; then echo "working tree is dirty — commit or stash first." >&2; exit 2; fi
SCOPE_LABEL="agent-${ONLY_AGENT}"; SCOPE_DESC="agent '${ONLY_AGENT}' (incremental)"
SCOPE_INSTR="IMPORTANT: restrict this run to ONLY the agent '${ONLY_AGENT}' and the fixtures that target it; skip every other agent and skill."
TRIALS_DIR="$(mktemp -d)"; trap 'rm -rf "$TRIALS_DIR"' EXIT
echo "== eval (${SCOPE_LABEL}) — ${TRIALS} trial(s), dispatching (costs tokens) =="
emitted="$(_dispatch "$SCOPE_INSTR" "$TRIALS_DIR")"
[ "$emitted" -gt 0 ] || { echo "no trials produced results — nothing to update." >&2; exit 1; }
_grade_variance "$ONLY_AGENT" "$TRIALS_DIR"

if git diff --quiet -- evals/baseline.json; then
  echo "baseline unchanged — no regression/improvement to record. No PR opened."; exit 0
fi
BRANCH="eval/${SCOPE_LABEL}-${STAMP}"
git checkout -b "$BRANCH" >/dev/null 2>&1 || { echo "branch create failed" >&2; exit 2; }
git add evals/baseline.json
git commit -q -m "test(evals): refresh baseline — ${SCOPE_LABEL} run (${STAMP})

${SCOPE_DESC} agent-eval run (${emitted} trial(s)); evals/baseline.json merged
(this scope's pairs updated, others untouched). Generated by run-full-eval.sh."
git push -u origin "$BRANCH" >/dev/null 2>&1 || { echo "push failed" >&2; exit 2; }
PR_URL="$(gh pr create --title "test(evals): refresh baseline — ${SCOPE_LABEL} run (${STAMP})" \
  --body "Automated agent-eval run via \`scripts/run-full-eval.sh\` — scope: **${SCOPE_DESC}**, ${emitted} trial(s).

Merges into \`evals/baseline.json\` (this scope's pairs updated, all others untouched — incremental-safe). Review the diff for **regressions** or **improvements**." 2>/dev/null)"
echo "opened: $PR_URL"
gh pr merge "$(echo "$PR_URL" | grep -oE '[0-9]+$')" --auto --squash --delete-branch >/dev/null 2>&1 \
  && echo "auto-merge enabled" || echo "could not enable auto-merge (enable manually)"
