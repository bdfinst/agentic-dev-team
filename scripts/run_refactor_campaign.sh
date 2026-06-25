#!/usr/bin/env bash
# Launch the full refactor-granularity campaign, sharded by arm (9 parallel
# processes). Each shard runs all 4 tasks x N trials with resume, writing its own
# JSONL so concurrent appends never interleave. Re-running resumes (skips cells
# whose change3 row already exists). Merge the shards afterward for analysis.
set -u

TRIALS="${1:-13}"
MODEL="${2:-claude-sonnet-4-6}"
OUT="docs/experiments/data"
RR="${RG_RUN_ROOT:-/tmp/rg-campaign}"
mkdir -p "$OUT" "$RR"

ARMS="tdd-refactor \
test-after-refactor test-after-refactor-frozen \
test-after-continuous test-after-continuous-frozen \
test-after-refactor-split test-after-refactor-frozen-split \
test-after-continuous-split test-after-continuous-frozen-split"

echo "campaign start $(date -u +%FT%TZ): trials=$TRIALS model=$MODEL run_root=$RR"
pids=""
for a in $ARMS; do
  python3 scripts/run_refactor_experiment.py \
    --arm "$a" --trials "$TRIALS" --model "$MODEL" \
    --out "$OUT/refactor-granularity-$a.jsonl" \
    --run-root "$RR/$a" > "$RR/$a.log" 2>&1 &
  pids="$pids $!"
  echo "  launched $a (pid $!)"
done

echo "waiting on:$pids"
fail=0
for p in $pids; do
  wait "$p" || fail=$((fail+1))
done
echo "campaign done $(date -u +%FT%TZ): $fail shard(s) exited non-zero"
