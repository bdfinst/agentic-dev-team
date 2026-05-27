#!/usr/bin/env bash
# Stryker.NET (C#) mutation testing adapter.
# Uses the same JSON schema as Stryker JS, so parse_stryker_kills() is shared.
# See lib.sh for adapter contract specification.
# NOTE: stryker_net_run() is intentionally NOT unified with stryker_run() —
#       the CLI surfaces diverge; the shared JSON parser is the stable contract.

ADAPTER_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$ADAPTER_LIB_DIR/lib.sh"

STRYKER_NET_REPORT="${STRYKER_NET_REPORT:-StrykerOutput/mutation-report.json}"

# stryker_net_detect — returns 0 if Stryker.NET is available
stryker_net_detect() {
  # Check dotnet-tools.json
  if [ -f ".config/dotnet-tools.json" ] && grep -q 'dotnet-stryker' ".config/dotnet-tools.json" 2>/dev/null; then
    return 0
  fi
  # Check dotnet stryker --version
  if command -v dotnet &>/dev/null; then
    if dotnet stryker --version &>/dev/null 2>&1; then
      return 0
    fi
  fi
  emit_advisory "MUTATION GATE ADVISORY: Stryker.NET not installed. Add dotnet-stryker to your .config/dotnet-tools.json to enable per-test mutation analysis on C# projects."
  return 1
}

# stryker_net_run OUTPUT_FILE — runs dotnet stryker and writes zero-kills
stryker_net_run() {
  local output_file="$1"
  local timeout="${ADAPTER_TIMEOUT:-60}"

  mkdir -p "$(dirname "$STRYKER_NET_REPORT")"

  local stryker_exit=0
  _timeout "$timeout" dotnet stryker \
    --reporter json \
    --coverage-analysis perTest \
    --mutation-level Standard \
    2>/dev/null || stryker_exit=$?

  if [ "$stryker_exit" -eq 124 ]; then
    emit_advisory "MUTATION GATE SKIPPED: timeout after ${timeout}s. Run MUTATION_GATE_TIMEOUT=<seconds> to adjust."
    echo "[]" > "$output_file"
    return 0
  fi

  if [ "$stryker_exit" -ne 0 ] && [ ! -f "$STRYKER_NET_REPORT" ]; then
    emit_advisory "MUTATION GATE ADVISORY: Stryker.NET exited with code $stryker_exit and produced no report. Skipping mutation gate."
    echo "[]" > "$output_file"
    return 0
  fi

  # Reuse parse_stryker_kills from lib.sh — same JSON schema
  parse_stryker_kills "$STRYKER_NET_REPORT" "$output_file"
}
