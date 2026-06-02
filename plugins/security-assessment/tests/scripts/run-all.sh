#!/usr/bin/env bash
# run-all.sh — shell-test runner for plugins/agentic-security-assessment/scripts/.
#
# Discovers every *.test.sh under this directory (tests/scripts/) and runs
# each in a clean subshell. Prints `PASS: <name>` or `FAIL: <name>` per test.
# Exits 0 only if every test exits 0.
#
# Self-test: run-all.self-test.sh creates a synthetic always-failing test
# case and asserts this runner exits non-zero and prints `FAIL: <name>` to
# stdout. The self-test is discovered and run like any other test.
#
# Usage:
#   bash tests/scripts/run-all.sh
#
# Exit codes:
#   0   all discovered tests passed
#   1   one or more tests failed
#   3   no *.test.sh files found (likely a layout mistake)

set -uo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"

PASS=0
FAIL=0
TOTAL=0
FAILED_NAMES=""

# Portable discovery — `while read` works on bash 3.2+.
while IFS= read -r test_file; do
  TOTAL=$((TOTAL+1))
  name="$(basename "$test_file" .test.sh)"
  if bash "$test_file" >/dev/null 2>&1; then
    echo "PASS: $name"
    PASS=$((PASS+1))
  else
    echo "FAIL: $name"
    FAIL=$((FAIL+1))
    FAILED_NAMES="${FAILED_NAMES}${name} "
  fi
done < <(find "$DIR" -maxdepth 2 -name '*.test.sh' -type f 2>/dev/null | sort)

if [[ $TOTAL -eq 0 ]]; then
  echo "run-all.sh: no *.test.sh files found under $DIR" >&2
  exit 3
fi

echo "---"
echo "Total: $TOTAL, Passed: $PASS, Failed: $FAIL"

if [[ $FAIL -gt 0 ]]; then
  echo "Failing tests: ${FAILED_NAMES% }" >&2
  exit 1
fi
exit 0
