#!/usr/bin/env bats
# Opt-in performance gate. AC23.
#
# After the single-process Python rewrite the builder runs ~0.17s for
# the real corpus on Apple Silicon. The threshold here is the spec's
# original target: 10 sequential rebuilds finish under 5s (500ms per
# build ceiling). Generous enough for slower runners while still
# catching meaningful regressions.
#
# Gated by KNOWLEDGE_INDEX_PERF=1 so default test runs stay fast.

BUILDER="$BATS_TEST_DIRNAME/../../plugins/dev-team/hooks/lib/build-knowledge-index.sh"

setup() {
  if [[ "${KNOWLEDGE_INDEX_PERF:-0}" != "1" ]]; then
    skip "set KNOWLEDGE_INDEX_PERF=1 to run the perf gate"
  fi
}

@test "perf: 10 sequential rebuilds of the real corpus finish under 5s" {
  local start_ns end_ns
  start_ns=$(python3 -c 'import time; print(int(time.time()*1000000000))')
  local i=0
  while (( i < 10 )); do
    bash "$BUILDER" >/dev/null
    i=$((i + 1))
  done
  end_ns=$(python3 -c 'import time; print(int(time.time()*1000000000))')
  local elapsed_ms=$(( (end_ns - start_ns) / 1000000 ))
  echo "elapsed_ms=$elapsed_ms (ceiling: <5000ms = 500ms per build)" >&3
  (( elapsed_ms < 5000 ))
}
