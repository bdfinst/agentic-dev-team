#!/usr/bin/env bash
# Self-updating public progress feed for the refactor-granularity campaign.
# Regenerates docs/experiments/refactor-granularity-progress.md and pushes it to
# the current branch every INTERVAL seconds, until the campaign's runner
# processes are gone. Runs in the sandbox (no assistant tokens). Uses [skip ci]
# so progress commits do not trigger CI.
set -u
BRANCH="${1:-claude/inspiring-cerf-552b8x}"
INTERVAL="${2:-600}"
FILE="docs/experiments/refactor-granularity-progress.md"
MAX=80

refresh() {
  python3 scripts/refactor_progress.py --ts "$(date -u +%FT%TZ)" > "$FILE"
  git add "$FILE"
  if ! git diff --staged --quiet; then
    git commit -q -m "docs: refresh refactor-granularity live progress [skip ci]" \
      -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
    git pull --rebase -q origin "$BRANCH" 2>/dev/null || true
    git push -q origin "$BRANCH" 2>/dev/null || true
  fi
}

i=0
while [ "$i" -lt "$MAX" ]; do
  refresh
  # stop once the campaign runner processes are gone
  if ! pgrep -f run_refactor_experiment.py >/dev/null 2>&1; then
    echo "campaign finished; final feed refresh done"
    refresh
    break
  fi
  sleep "$INTERVAL"
  i=$((i+1))
done
echo "feed loop exit after $i cycles"
