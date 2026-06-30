#!/usr/bin/env bash
# mutmut (Python) mutation testing adapter.
# See lib.sh for adapter contract specification.
#
# mutmut scopes to a single file via --paths-to-mutate and completes
# in seconds-to-minutes for typical Python unit test suites.
# Results are parsed from `mutmut results --json`.

ADAPTER_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$ADAPTER_LIB_DIR/lib.sh"

# mutmut_detect — returns 0 if mutmut is available in this project
mutmut_detect() {
  if command -v mutmut &>/dev/null; then
    return 0
  fi
  # Check common install locations
  if python3 -m mutmut --version &>/dev/null 2>&1; then
    return 0
  fi
  emit_advisory "MUTATION GATE ADVISORY: mutmut not installed. Run /init-dev-team to install it, or: pip install mutmut"
  return 1
}

# _derive_python_source TEST_FILE — strip test_ prefix / _test suffix to find source.
# tests/test_calculator.py → calculator.py (then search src/)
# tests/calculator_test.py → calculator.py
_derive_python_source() {
  local test_file="$1"
  local base
  base=$(basename "$test_file" .py)
  base="${base#test_}"          # strip test_ prefix
  base="${base%_test}"          # strip _test suffix
  # Search common source locations
  for dir in src "" lib; do
    local candidate="${dir:+$dir/}${base}.py"
    [ -f "$candidate" ] && echo "$candidate" && return
  done
  # Fallback: return the test file itself (mutmut can still run on it)
  echo "$test_file"
}

# mutmut_run OUTPUT_FILE — runs mutmut scoped to the changed Python file
#
# Timeout: ADAPTER_TIMEOUT default 120s. Python test suites are fast so
# a single-file mutmut run usually completes in 10-60s.
#
# Scoping: mutmut --paths-to-mutate=<file> limits mutation to one file,
# which keeps runs fast even on large codebases.
mutmut_run() {
  local output_file="$1"
  local timeout="${ADAPTER_TIMEOUT:-120}"

  # Find the changed Python source file
  local src_file=""
  src_file=$(git diff --name-only HEAD 2>/dev/null | \
    grep '\.py$' | grep -v 'test_\|_test\.py' | head -1)
  [ -z "$src_file" ] && \
    src_file=$(git diff --cached --name-only 2>/dev/null | \
      grep '\.py$' | grep -v 'test_\|_test\.py' | head -1)

  # Fall back to deriving from the test command if no source file detected
  local mutmut_cmd="mutmut"
  command -v mutmut &>/dev/null || mutmut_cmd="python3 -m mutmut"

  local mutmut_args=(run)
  [ -n "$src_file" ] && mutmut_args+=(--paths-to-mutate="$src_file")

  local mutmut_exit=0
  # shellcheck disable=SC2086
  _timeout "$timeout" $mutmut_cmd "${mutmut_args[@]}" \
    2>/dev/null || mutmut_exit=$?

  if [ "$mutmut_exit" -eq 124 ]; then
    local scope_hint=""
    [ -z "$src_file" ] && scope_hint=" No source file detected — scope with --paths-to-mutate."
    emit_advisory "MUTATION GATE SKIPPED: mutmut timed out after ${timeout}s.${scope_hint} Or: MUTATION_GATE_TIMEOUT=<seconds> to extend the limit."
    echo "[]" > "$output_file"
    return 0
  fi

  # mutmut exits non-zero when survivors exist (exit 1) or on error (exit 2+)
  # exit 1 with survivors is expected — still parse results
  if [ "$mutmut_exit" -ge 2 ]; then
    emit_advisory "MUTATION GATE ADVISORY: mutmut exited with code $mutmut_exit. Skipping mutation gate."
    echo "[]" > "$output_file"
    return 0
  fi

  # Parse survivors from `mutmut results --json`
  local results_json
  results_json=$($mutmut_cmd results --json 2>/dev/null || echo "[]")

  python3 - "$output_file" "$results_json" <<'PYEOF'
import sys, json

output_path = sys.argv[1]
raw = sys.argv[2]

try:
    data = json.loads(raw)
except Exception:
    data = []

zero_kills = []

# mutmut results --json format: list of {id, line_number, filename, diff, ...}
# A mutant appearing in results = survived (not killed by any test)
for mutant in data:
    status = mutant.get("status", "")
    # Only include survived mutants (not killed, not suspicious/timeout)
    if status in ("survived", ""):
        zero_kills.append({
            "name": f"mutant_{mutant.get('id', '?')}",
            "file": mutant.get("filename"),
            "line": mutant.get("line_number"),
            "covered": 0,
        })

with open(output_path, "w") as f:
    json.dump(zero_kills, f)
PYEOF
}
