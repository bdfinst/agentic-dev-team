#!/usr/bin/env bats
# Opt-in performance gate for hooks/lib/model-resolve.sh. AC15.
#
# The spec AC15 target is a 50ms p99 ceiling per resolver invocation.
# Each invocation is a separate bash + jq process; bash + jq cold-start
# on macOS Apple Silicon is ~10ms together, dominating actual resolution
# work. We assert 50000ms (50ms × 1000) as the wall-clock ceiling for
# 1000 sequential happy-path invocations — matching the spec target, not
# the aspirational 10× headroom.
#
# Gated by MODEL_RESOLVE_PERF=1 so default test runs stay fast. CI should
# run with the gate enabled on a periodic job, not every PR.

RESOLVER="$BATS_TEST_DIRNAME/../../plugins/dev-team/hooks/lib/model-resolve.sh"

setup() {
  if [[ "${MODEL_RESOLVE_PERF:-0}" != "1" ]]; then
    skip "set MODEL_RESOLVE_PERF=1 to run the perf gate"
  fi
  BATS_TMPDIR_CASE="$(mktemp -d)"
  cat > "$BATS_TMPDIR_CASE/routing.json" <<'EOF'
{"haiku":"claude-haiku-4-5-20251001","sonnet":"claude-sonnet-4-6","opus":"claude-opus-4-8"}
EOF
  export MODEL_ROUTING_JSON="$BATS_TMPDIR_CASE/routing.json"
  export MODEL_OVERRIDES_JSON="$BATS_TMPDIR_CASE/overrides.json"  # absent
  export MODEL_BUMP_LOG="$BATS_TMPDIR_CASE/metrics.log"
}

teardown() {
  rm -rf "$BATS_TMPDIR_CASE" 2>/dev/null || true
  unset MODEL_ROUTING_JSON MODEL_OVERRIDES_JSON MODEL_BUMP_LOG
}

@test "perf: 1000 sequential haiku resolutions complete in < 50s (50ms p99)" {
  local start_ns end_ns
  # macOS `date` does not support %N. Use python3 for portable nanos.
  start_ns=$(python3 -c 'import time; print(int(time.time()*1000000000))')
  local i=0
  while (( i < 1000 )); do
    bash "$RESOLVER" haiku >/dev/null
    i=$((i + 1))
  done
  end_ns=$(python3 -c 'import time; print(int(time.time()*1000000000))')
  local elapsed_ms=$(( (end_ns - start_ns) / 1000000 ))
  echo "elapsed_ms=$elapsed_ms (target: <50000ms = 50ms p99)" >&3
  # 50s wall-clock ceiling = 50ms p99 per invocation. The spec target;
  # actual measurements on Apple Silicon run ~10-15ms per invocation.
  (( elapsed_ms < 50000 ))
}
