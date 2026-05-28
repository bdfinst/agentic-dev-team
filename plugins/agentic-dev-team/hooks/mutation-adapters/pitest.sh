#!/usr/bin/env bash
# pitest (Java/Kotlin) mutation testing adapter.
# See lib.sh for adapter contract specification.

ADAPTER_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$ADAPTER_LIB_DIR/lib.sh"

PITEST_REPORT="${PITEST_REPORT:-target/pit-reports/mutations.xml}"

# pitest_detect — returns 0 if pitest is configured in this project
pitest_detect() {
  if [ -f "pom.xml" ] && grep -q 'pitest' "pom.xml" 2>/dev/null; then
    return 0
  fi
  if [ -f "build.gradle" ] && grep -q 'pitest' "build.gradle" 2>/dev/null; then
    return 0
  fi
  if [ -f "build.gradle.kts" ] && grep -q 'pitest' "build.gradle.kts" 2>/dev/null; then
    return 0
  fi
  emit_advisory "MUTATION GATE ADVISORY: pitest not found. Run /init-dev-team to configure it, or add the pitest-maven plugin to pom.xml / pitest plugin to build.gradle manually."
  return 1
}

# pitest_parse XML_FILE OUTPUT_FILE — parses zero-kill tests from pitest mutations.xml
pitest_parse() {
  local xml_file="$1"
  local output_file="$2"
  local runner_stdout="${ADAPTER_RUNNER_STDOUT:-}"

  if [ ! -f "$xml_file" ]; then
    emit_advisory "MUTATION GATE ADVISORY: pitest report not found at $xml_file. Skipping mutation gate."
    echo "[]" > "$output_file" 2>/dev/null || true
    return 0
  fi

  if [ -z "$runner_stdout" ]; then
    # No test list available — fall back to aggregate advisory
    local killed survived total
    # grep -c exits 1 on no-match; use || assignment to always get a number
    killed=$(grep -c 'status="KILLED"' "$xml_file" 2>/dev/null) || killed=0
    survived=$(grep -c 'status="SURVIVED"' "$xml_file" 2>/dev/null) || survived=0
    total=$(( killed + survived ))
    emit_advisory "MUTATION GATE ADVISORY: pitest completed (${killed}/${total} mutants killed) but per-test data unavailable — runner stdout was not captured. Manual review recommended."
    echo "[]" > "$output_file" 2>/dev/null || true
    return 0
  fi

  python3 - "$xml_file" "$output_file" "$runner_stdout" <<'PYEOF'
import sys, re, json

xml_path, output_path, runner_stdout = sys.argv[1], sys.argv[2], sys.argv[3]

# Parse killing tests from XML
killing_set = set()
with open(xml_path) as f:
    content = f.read()
for m in re.finditer(r'<killingTest>([^<]+)</killingTest>', content):
    killing_set.add(m.group(1).strip())

# Parse test method list from runner stdout
# Supports Maven surefire patterns: "com.example.CalculatorTest.methodName"
test_methods = set()
for line in runner_stdout.splitlines():
    line = line.strip()
    # Full qualified method: com.example.ClassName.methodName
    if re.match(r'^[\w.]+\.\w+$', line) and '.' in line:
        test_methods.add(line)
    # Maven surefire: "testAdd  Time elapsed: ..."
    m = re.match(r'^(\w+)\s+(Time elapsed|PASS|FAIL)', line)
    if m:
        test_methods.add(m.group(1))

# Zero-kill = test method in test list but not in any killingTest
zero_kills = []
for test in sorted(test_methods - killing_set):
    zero_kills.append({
        "name": test,
        "file": None,
        "line": None,
        "covered": 0  # pitest XML doesn't provide per-test coverage counts
    })

with open(output_path, "w") as f:
    json.dump(zero_kills, f)
PYEOF
}

# _extract_test_class COMMAND — extracts test class from mvn -Dtest= flag if present
_extract_test_class() {
  local cmd="$1"
  echo "$cmd" | grep -oE '\-Dtest=[^ ]+' | sed 's/-Dtest=//' || true
}

# pitest_run OUTPUT_FILE — runs pitest and writes zero-kills
pitest_run() {
  local output_file="$1"
  local timeout="${ADAPTER_TIMEOUT:-60}"
  local cmd="${ADAPTER_COMMAND:-}"

  mkdir -p "$(dirname "$PITEST_REPORT")"

  local target_tests=""
  local test_class
  test_class=$(_extract_test_class "$cmd")
  [ -n "$test_class" ] && target_tests="-DtargetTests=$test_class"

  local pitest_exit=0
  # shellcheck disable=SC2086
  _timeout "$timeout" mvn pitest:mutationCoverage \
    -DoutputFormats=XML \
    -DtimestampedReports=false \
    $target_tests \
    2>/dev/null || pitest_exit=$?

  if [ "$pitest_exit" -eq 124 ]; then
    emit_advisory "MUTATION GATE SKIPPED: timeout after ${timeout}s. Run MUTATION_GATE_TIMEOUT=<seconds> to adjust."
    echo "[]" > "$output_file"
    return 0
  fi

  if [ "$pitest_exit" -ne 0 ] && [ ! -f "$PITEST_REPORT" ]; then
    emit_advisory "MUTATION GATE ADVISORY: pitest exited with code $pitest_exit and produced no report. Skipping mutation gate."
    echo "[]" > "$output_file"
    return 0
  fi

  pitest_parse "$PITEST_REPORT" "$output_file"
}
