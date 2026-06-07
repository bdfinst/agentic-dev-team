#!/usr/bin/env bash
# run-full-eval-parallel.sh — harvest the agent-eval corpus in PARALLEL batches,
# isolated by git worktrees, then reconcile deterministically into one baseline
# and open an auto-merge PR.
#
# Why worktrees: the serial sweep (run-full-eval.sh) shares ONE working tree, so
# it cannot be parallelized — every dispatch writes the same `actuals.json` at the
# repo root, every grade does a read-modify-write of `evals/baseline.json`, and
# every checkpoint/commit shares one git index. A worktree per batch gives each
# batch its own cwd, index, and `actuals.json`, so the only *expensive* part (the
# live `claude -p` dispatch) runs concurrently without collisions.
#
# Why the grade is NOT parallelized: `evals/baseline.json` is a flat `passing`
# pair-list merged as `(existing | passed) - failed`. A batch that never ran agent
# X still carries X's old passing pairs, so unioning per-batch baselines would
# RESURRECT pairs another batch correctly removed. The safe design is therefore:
# parallelize dispatch only; collect each agent's trial actuals into a disjoint
# per-agent dir; then run ONE deterministic, model-free grade over the union,
# scoped (`--only`) to the agents that actually produced actuals so a failed
# dispatch never wipes an agent's baseline.
#
# Partition unit is the AGENT: an agent's trials must be graded together (pass@k /
# variance), so an agent is never split across batches. Round-robin keeps batches
# balanced. Real speedup is bounded by your account's API rate/token pace, not by
# --jobs; burns budget faster too. N=2-4 is the sane range (#142 pace guidance).
#
# Resumable: per-agent trials live under .eval-parallel/<agent>/ (gitignored) with
# a `.done` marker. Re-run to pick up only the agents still missing; --fresh wipes
# it. Already-done agents still contribute to the final grade on resume.
#
# Usage:  bash scripts/run-full-eval-parallel.sh [TRIALS] [--jobs N] [--fresh]
#         TRIALS default 1, --jobs default 3.
# Env:    ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN, plus `claude` + `gh`.
# Exit:   0 ok, 2 missing prereq/dirty tree, 1 run produced nothing.

set -uo pipefail
MAIN_ROOT="$(git rev-parse --show-toplevel)" || exit 2
cd "$MAIN_ROOT" || exit 2

TRIALS=1; JOBS=3; FRESH=0
while [ $# -gt 0 ]; do
  case "$1" in
    --jobs)  JOBS="${2:-}"; shift 2 ;;
    --fresh) FRESH=1; shift ;;
    [0-9]*)  TRIALS="$1"; shift ;;
    *) echo "usage: run-full-eval-parallel.sh [TRIALS] [--jobs N] [--fresh]" >&2; exit 2 ;;
  esac
done
case "$JOBS" in ''|*[!0-9]*) echo "--jobs must be a positive integer" >&2; exit 2 ;; esac
[ "$JOBS" -ge 1 ] || { echo "--jobs must be >= 1" >&2; exit 2; }

STAMP="$(date -u +%Y%m%d-%H%M%S)"
RUN_DIR="$MAIN_ROOT/.eval-parallel"          # gitignored: per-agent trials + resume
WT_BASE="$(mktemp -d)"                        # worktrees live OUTSIDE the repo tree

# --- prerequisites ----------------------------------------------------------
for t in claude gh jq python3 git; do
  command -v "$t" >/dev/null 2>&1 || { echo "missing required tool: $t" >&2; exit 2; }
done
if [ -z "${ANTHROPIC_API_KEY:-}" ] && [ -z "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
  echo "no ANTHROPIC_API_KEY / CLAUDE_CODE_OAUTH_TOKEN — the live eval needs creds." >&2
  exit 2
fi
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "working tree is dirty — commit or stash first." >&2; exit 2
fi

# Isolate everything on a fresh branch as the FIRST step, so a failed push never
# strands work on your base branch and the run is visible from the start.
BASE_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
BRANCH="eval/sweep-parallel-${STAMP}"
COMMITTED=0
git checkout -b "$BRANCH" >/dev/null 2>&1 || { echo "branch create failed: $BRANCH" >&2; exit 2; }
echo "== branch: $BRANCH (from $BASE_BRANCH) =="

# --- cleanup: always tear down worktrees, even on interrupt -----------------
cleanup() {
  local wt
  for wt in "$WT_BASE"/b*; do
    if [ -d "$wt" ]; then git worktree remove --force "$wt" >/dev/null 2>&1 || true; fi
  done
  git worktree prune >/dev/null 2>&1 || true
  rm -rf "$WT_BASE"
  # Created the sweep branch but never committed (no baseline change or an early
  # failure)? Don't strand the user on an empty branch — return to base, drop it.
  if [ "${COMMITTED:-0}" -eq 0 ] && [ -n "${BRANCH:-}" ]; then
    git checkout -f "${BASE_BRANCH:-main}" >/dev/null 2>&1 || true
    git branch -D "$BRANCH" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

[ "$FRESH" = 1 ] && rm -rf "$RUN_DIR"
mkdir -p "$RUN_DIR"

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

# --- the corpus's agents, and which still need dispatching ------------------
# (read loop, not `mapfile` — the latter is bash 4+, absent on macOS's bash 3.2)
ALL_AGENTS=()
while IFS= read -r _agent; do
  [ -n "$_agent" ] && ALL_AGENTS+=("$_agent")
done < <(jq -r '.applicableAgents[]?' evals/expected/*.json 2>/dev/null | sort -u)
[ "${#ALL_AGENTS[@]}" -gt 0 ] || { echo "no applicableAgents in evals/expected — nothing to do." >&2; exit 1; }

TODO=()
for a in "${ALL_AGENTS[@]}"; do
  if [ -f "$RUN_DIR/$a/.done" ]; then echo "skip (done): $a"; else TODO+=("$a"); fi
done

# --- dispatch one batch's agents inside a PRE-CREATED worktree (bg job) ------
# The worktree is created serially by the caller (git worktree add isn't safe to
# race), so this function only does live dispatch — no shared-state mutation
# beyond each agent's own disjoint .eval-parallel/<agent>/ dir.
# Args: <batch-index> <worktree-path> <agent>...
run_batch() {
  local bi="$1" wt="$2"; shift 2
  (
    cd "$wt" || exit 1
    mkdir -p .claude/evals
    ln -sfn "$wt/evals/fixtures" .claude/evals/fixtures
    ln -sfn "$wt/evals/expected" .claude/evals/expected
    local agent out prompt n good
    for agent in "$@"; do
      out="$RUN_DIR/$agent"; mkdir -p "$out"
      prompt="${PROMPT_BASE}"$'\n\n'"IMPORTANT: restrict this run to ONLY the agent '${agent}' and the fixtures that target it; skip every other agent and skill."
      good=0
      for n in $(seq 1 "$TRIALS"); do
        rm -f actuals.json
        claude -p "$prompt" --output-format json --max-turns 200 --model claude-sonnet-4-6 \
          --allowedTools "Read" "Glob" "Grep" "Write" "Agent" \
                         "Skill(review-agent *)" "Skill(test-design-advisor *)" \
          >/dev/null 2>&1 || true
        if jq -e . actuals.json >/dev/null 2>&1; then
          cp actuals.json "$out/trial-${n}.json"; good=$((good + 1))
        fi
      done
      rm -f actuals.json
      if [ "$good" -gt 0 ]; then
        touch "$out/.done"; echo "[batch $bi] done: $agent ($good/$TRIALS trial(s))"
      else
        echo "[batch $bi] NO actuals: $agent — left un-done for resume" >&2
      fi
    done
  )
}

# --- partition TODO round-robin into JOBS batches, dispatch in parallel ------
if [ "${#TODO[@]}" -gt 0 ]; then
  declare -a BATCH=()
  for ((i = 0; i < ${#TODO[@]}; i++)); do
    bi=$(( i % JOBS ))
    BATCH[bi]="${BATCH[bi]:-} ${TODO[i]}"
  done
  echo "== dispatching ${#TODO[@]} agent(s) across up to $JOBS batch(es), $TRIALS trial(s) each =="
  pids=()
  for ((bi = 0; bi < JOBS; bi++)); do
    [ -n "${BATCH[$bi]:-}" ] || continue
    wt="$WT_BASE/b$bi"
    if ! git worktree add --detach "$wt" HEAD >/dev/null 2>&1; then   # serial: no race
      echo "[batch $bi] worktree add failed — skipping batch" >&2; continue
    fi
    # shellcheck disable=SC2086
    run_batch "$bi" "$wt" ${BATCH[$bi]} &
    pids+=("$!")
  done
  fail=0
  # Guard the expansion: under `set -u`, bash 3.2 errors on "${empty[@]}".
  if [ "${#pids[@]}" -gt 0 ]; then
    for p in "${pids[@]}"; do wait "$p" || fail=1; done
  fi
  [ "$fail" -eq 0 ] || echo "warning: a batch exited non-zero; reconciling whatever landed." >&2
else
  echo "== all agents already harvested in $RUN_DIR — skipping dispatch, reconciling =="
fi

# ===================== DETERMINISTIC RECONCILE (serial) =====================
# Collect each agent's FIRST good trial; union them (disjoint agent keys, so
# jq's recursive `*` merge loses nothing) into one actuals for a single graded
# baseline write. SUCCEEDED scopes the grade so absent agents keep their pairs.
SUCCEEDED=(); FIRST_TRIALS=()
for a in "${ALL_AGENTS[@]}"; do
  ft="$(find "$RUN_DIR/$a" -name 'trial-*.json' 2>/dev/null | sort | head -1)"
  [ -n "$ft" ] || continue
  SUCCEEDED+=("$a"); FIRST_TRIALS+=("$ft")
done
if [ "${#SUCCEEDED[@]}" -eq 0 ]; then
  echo "no actuals produced by any agent — nothing to grade." >&2; exit 1
fi

COMBINED="$(mktemp)"
jq -s 'reduce .[] as $x ({}; . * $x)' "${FIRST_TRIALS[@]}" > "$COMBINED"
ONLY="$(IFS=','; echo "${SUCCEEDED[*]}")"
echo "== grading ${#SUCCEEDED[@]} agent(s) into evals/baseline.json =="
python3 scripts/eval_grade.py --actuals "$COMBINED" --only "$ONLY" \
  --write-baseline evals/baseline.json || { echo "grade failed" >&2; rm -f "$COMBINED"; exit 1; }
rm -f "$COMBINED"

# Variance trend (local, like the serial sweep): per agent with >1 trial.
for a in "${SUCCEEDED[@]}"; do
  tdir="$RUN_DIR/$a"
  [ "$(find "$tdir" -name 'trial-*.json' | wc -l)" -gt 1 ] || continue
  ve="$tdir/expected"; mkdir -p "$ve"
  for ef in evals/expected/*.json; do
    jq -e --arg a "$a" '.applicableAgents // [] | index($a)' "$ef" >/dev/null 2>&1 && cp "$ef" "$ve/"
  done
  python3 scripts/eval_variance.py --trials-dir "$tdir" --expected-dir "$ve" \
    --append metrics/eval-variance.jsonl -o memory/eval-variance.json >/dev/null 2>&1 || true
done

# ===================== COMMIT + AUTO-MERGE PR (one PR) ======================
# Branch already exists (created up front). The trap restores base + drops it
# if we never commit below.
if git diff --quiet -- evals/baseline.json; then
  echo "== baseline unchanged across the harvest — nothing to commit, no PR. =="
  echo "   (trials kept in $RUN_DIR; re-run with --fresh for a clean re-harvest.)"
  exit 0
fi

git add evals/baseline.json
git commit -q -m "test(evals): parallel sweep baseline refresh (${STAMP})

Harvested ${#SUCCEEDED[@]} agent(s) across $JOBS worktree-isolated batch(es) via
run-full-eval-parallel.sh, then graded once (deterministic) into evals/baseline.json
scoped to the agents that produced actuals. Variance appended to the local trend."
COMMITTED=1
echo "== committed baseline on $BRANCH; per-agent trials are in $RUN_DIR =="

# Push with the pre-push hook VISIBLE — it runs scripts/ci-local.sh and BLOCKS
# the push on failure. A single attempt: the hook is deterministic, so retrying
# just re-runs the local CI mirror; for a transient network drop, re-run the
# printed `git push` by hand.
echo "== pushing $BRANCH (pre-push runs the local CI mirror — can take a minute)… =="
if git push -u origin "$BRANCH"; then
  PR_URL="$(gh pr create --title "test(evals): parallel sweep baseline refresh (${STAMP})" \
    --body "Parallel full-corpus harvest via \`run-full-eval-parallel.sh\` — dispatch ran in
$JOBS git-worktree-isolated batches, reconciled by a single deterministic grade into
\`evals/baseline.json\` (scoped to the ${#SUCCEEDED[@]} agent(s) that produced actuals, so a
failed dispatch can't drop an agent's pairs). Review the diff for **regressions** (pairs
dropped) or **improvements** (pairs newly passing). Variance appended to the local trend." 2>/dev/null)"
  echo "opened: $PR_URL"
  gh pr merge "$(echo "$PR_URL" | grep -oE '[0-9]+$')" --auto --squash --delete-branch >/dev/null 2>&1 \
    && echo "auto-merge enabled" || echo "could not enable auto-merge (enable manually)"
  echo "   (trials kept in $RUN_DIR; re-run with --fresh for a clean re-harvest.)"
else
  echo "" >&2
  echo "push failed — see the pre-push / CI output ABOVE for the actual reason." >&2
  echo "Your harvest is safe: committed on branch '$BRANCH' (nothing lost)." >&2
  echo "  • fix the gate, then re-push:  git push -u origin $BRANCH" >&2
  echo "  • or bypass the local hook:    HUSKY=0 git push -u origin $BRANCH" >&2
  exit 2
fi
