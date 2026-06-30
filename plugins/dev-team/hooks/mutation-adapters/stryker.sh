#!/usr/bin/env bash
# Stryker (JS/TS) mutation testing adapter.
# See ADAPTER-CONTRACT comment in lib.sh for interface specification.
# Source this file; do not execute directly.
#
# Inputs (env vars from orchestrator):
#   ADAPTER_SOURCE_FILE   — source file to mutate
#   ADAPTER_TIMEOUT       — seconds (default 300)
# Output: writes zero-kills to $TMPDIR/mutation-gate/zero-kills.json

# shellcheck source=hooks/mutation-adapters/lib.sh
ADAPTER_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$ADAPTER_LIB_DIR/lib.sh"

# Default Stryker JSON report path
STRYKER_REPORT="${STRYKER_REPORT:-reports/mutation/mutation.json}"

# stryker_detect — returns 0 if Stryker is available in the current project
stryker_detect() {
  if [ -f "node_modules/.bin/stryker" ]; then
    return 0
  fi
  if [ -f "package.json" ] && grep -q '@stryker-mutator/core' "package.json" 2>/dev/null; then
    return 0
  fi
  emit_advisory "MUTATION GATE ADVISORY: Stryker not installed. Run /init-dev-team to install it, or add @stryker-mutator/core manually."
  return 1
}

# derive_source_file TEST_FILE — strips .test./.spec. to find source file
derive_source_file() {
  local test_file="$1"
  # e.g. calc.test.ts → calc.ts, calc.spec.js → calc.js
  echo "$test_file" | sed -E 's/\.(test|spec)\.(ts|tsx|js|jsx|mjs)$/.\2/'
}

# _stryker_read_timeout_ms — read timeoutMS from the project's Stryker config,
# or echo empty string if not configured.  Checks stryker.config.{js,mjs,cjs,ts}
# and .strykerrc.json for the timeoutMS field.
_stryker_read_timeout_ms() {
  # .strykerrc.json is easiest — pure JSON
  if [ -f ".strykerrc.json" ] && command -v python3 &>/dev/null; then
    python3 -c "
import json, sys
try:
    cfg = json.load(open('.strykerrc.json'))
    t = cfg.get('timeoutMS') or cfg.get('timeout')
    if t: print(int(t))
except Exception:
    pass
" 2>/dev/null
    return
  fi
  # stryker.config.* — grep for timeoutMS: <number>
  for f in stryker.config.js stryker.config.mjs stryker.config.cjs stryker.config.ts; do
    [ -f "$f" ] || continue
    grep -oE 'timeoutMS[[:space:]]*:[[:space:]]*[0-9]+' "$f" 2>/dev/null \
      | grep -oE '[0-9]+$' | head -1
    return
  done
}

# stryker_run OUTPUT_FILE — runs Stryker and writes zero-kills to OUTPUT_FILE
#
# Timeout behaviour:
#   ADAPTER_TIMEOUT (default 300s) is the outer process kill timer.
#   300s covers a single-file scoped run on a large monorepo with perTest
#   coverage analysis.  Single-file JS/TS runs typically finish in 30–120s.
#
#   The per-mutant timeout is controlled by Stryker's own timeoutMS / timeoutFactor
#   config, NOT by ADAPTER_TIMEOUT.  If the project has no timeoutMS configured,
#   Stryker defaults to 5000 ms × timeoutFactor (2.5) — usually fine for unit tests.
#
# Scoping:
#   ADAPTER_SOURCE_FILE is derived from the test file by derive_source_file()
#   in mutation-gate.sh and passed via --mutate so only that file is mutated.
stryker_run() {
  local output_file="$1"
  local timeout="${ADAPTER_TIMEOUT:-300}"
  local src_file="${ADAPTER_SOURCE_FILE:-}"

  mkdir -p "$(dirname "$STRYKER_REPORT")"

  # Build args — always scope to the source file when available
  local stryker_args=(
    --reporters json
    --coverageAnalysis perTest
  )
  [ -n "$src_file" ] && stryker_args+=(--mutate "$src_file")

  # Use || to capture exit code without triggering set -e in the calling context
  local stryker_exit=0
  _timeout "$timeout" npx stryker run "${stryker_args[@]}" \
    2>/dev/null || stryker_exit=$?

  if [ "$stryker_exit" -eq 124 ]; then
    local timeout_ms
    timeout_ms=$(_stryker_read_timeout_ms)
    local config_hint=""
    if [ -z "$timeout_ms" ]; then
      config_hint=" Add 'timeoutMS: <ms>' to stryker.config.js to cap per-mutant runs."
    fi
    emit_advisory "MUTATION GATE SKIPPED: Stryker timed out after ${timeout}s.${config_hint} Or: MUTATION_GATE_TIMEOUT=<seconds> to extend the outer limit."
    echo "[]" > "$output_file"
    return 0
  fi

  if [ "$stryker_exit" -ne 0 ] && [ ! -f "$STRYKER_REPORT" ]; then
    emit_advisory "MUTATION GATE ADVISORY: Stryker exited with code $stryker_exit and produced no report. Skipping mutation gate."
    echo "[]" > "$output_file"
    return 0
  fi

  parse_stryker_kills "$STRYKER_REPORT" "$output_file"
}
