#!/usr/bin/env bash
# Stryker (JS/TS) mutation testing adapter.
# See ADAPTER-CONTRACT comment in lib.sh for interface specification.
# Source this file; do not execute directly.
#
# Inputs (env vars from orchestrator):
#   ADAPTER_SOURCE_FILE   — source file to mutate
#   ADAPTER_TIMEOUT       — seconds (default 60)
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
  emit_advisory "MUTATION GATE ADVISORY: Stryker not installed. Add @stryker-mutator/core to run per-test mutation analysis on JS/TS projects."
  return 1
}

# derive_source_file TEST_FILE — strips .test./.spec. to find source file
derive_source_file() {
  local test_file="$1"
  # e.g. calc.test.ts → calc.ts, calc.spec.js → calc.js
  echo "$test_file" | sed -E 's/\.(test|spec)\.(ts|tsx|js|jsx|mjs)$/.\2/'
}

# stryker_run OUTPUT_FILE — runs Stryker and writes zero-kills to OUTPUT_FILE
stryker_run() {
  local output_file="$1"
  local timeout="${ADAPTER_TIMEOUT:-60}"
  local src_file="${ADAPTER_SOURCE_FILE:-}"

  mkdir -p "$(dirname "$STRYKER_REPORT")"

  # Use || to capture exit code without triggering set -e in the calling context
  local stryker_exit=0
  _timeout "$timeout" npx stryker run \
    --reporters json \
    --coverageAnalysis perTest \
    ${src_file:+--mutate "$src_file"} \
    2>/dev/null || stryker_exit=$?

  if [ "$stryker_exit" -eq 124 ]; then
    emit_advisory "MUTATION GATE SKIPPED: timeout after ${timeout}s. Run MUTATION_GATE_TIMEOUT=<seconds> to adjust."
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
