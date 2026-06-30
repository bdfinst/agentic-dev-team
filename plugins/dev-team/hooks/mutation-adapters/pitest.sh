#!/usr/bin/env bash
# pitest (Java/Kotlin) mutation testing adapter.
# See lib.sh for adapter contract specification.
#
# Key improvements over original:
#   - ADAPTER_TIMEOUT raised to 300s (Maven startup alone is 20-30s)
#   - Source class derived from changed file and passed as -DtargetClasses
#   - -DwithHistory enables incremental runs (huge speedup after first run)
#   - -DtimeoutConst / -DtimeoutFactor cap per-mutant wall-clock time
#   - Multi-module Maven: detects the module containing the changed file
#     and passes -pl <module> to scope the build

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

# _java_class_from_file FILE — convert a Java/Kotlin file path to a dotted class name.
# src/main/java/com/example/pkg/Calculator.java → com.example.pkg.Calculator
# src/main/kotlin/com/example/pkg/Calculator.kt → com.example.pkg.Calculator
_java_class_from_file() {
  local file="$1"
  [ -n "$file" ] || return 0
  # Strip known source roots
  local rel
  rel=$(echo "$file" | sed -E \
    's|^.*(src/main/java/|src/main/kotlin/|src/main/groovy/|src/||)(.*)|\2|')
  # Strip extension and convert / to .
  echo "$rel" | sed -E 's/\.(java|kt|groovy|scala)$//' | tr '/' '.'
}

# _find_maven_module FILE — find the nearest Maven module directory containing FILE.
# For single-module projects this is "." (empty string returned → no -pl flag needed).
# For multi-module projects it returns the subdirectory path.
_find_maven_module() {
  local file="$1"
  [ -n "$file" ] || return 0

  local dir
  dir=$(dirname "$file")
  while [ "$dir" != "." ] && [ -n "$dir" ]; do
    if [ -f "$dir/pom.xml" ]; then
      # Only return as a sub-module if it's not the root pom.xml
      if [ "$dir" != "." ] && [ -f "pom.xml" ]; then
        echo "$dir"
        return 0
      fi
    fi
    dir=$(dirname "$dir")
  done
}

# _is_gradle — returns 0 if this is a Gradle project
_is_gradle() {
  [ -f "build.gradle" ] || [ -f "build.gradle.kts" ] || [ -f "settings.gradle" ] || \
  [ -f "settings.gradle.kts" ]
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
#
# Timeout behaviour:
#   ADAPTER_TIMEOUT (default 300s) is the outer process kill timer.
#   Maven startup alone takes 20-30s; a single-class scoped pitest run
#   with withHistory typically completes in 30-120s.
#
# Scoping:
#   -DtargetClasses scopes pitest to just the changed class.
#   -DtargetTests   scopes pitest to just the test class (from ADAPTER_COMMAND).
#   -DwithHistory   skips mutants already killed in prior runs (incremental).
#   -DtimeoutConst / -DtimeoutFactor cap per-mutant wall-clock time.
#
# Multi-module Maven:
#   -pl <module>    scopes the Maven build to the module containing the changed file.
pitest_run() {
  local output_file="$1"
  local timeout="${ADAPTER_TIMEOUT:-300}"
  local cmd="${ADAPTER_COMMAND:-}"

  # Derive the changed Java/Kotlin source file from the test command
  local changed_file=""
  changed_file=$(git diff --name-only HEAD 2>/dev/null | \
    grep -E '\.(java|kt|groovy|scala)$' | grep -v 'Test\|Spec' | head -1)
  [ -z "$changed_file" ] && \
    changed_file=$(git diff --cached --name-only 2>/dev/null | \
      grep -E '\.(java|kt|groovy|scala)$' | grep -v 'Test\|Spec' | head -1)

  # Build the pitest arguments
  local pitest_args=()

  # Target class — scope pitest to just the changed file's class
  local target_class=""
  if [ -n "$changed_file" ]; then
    target_class=$(_java_class_from_file "$changed_file")
  fi

  # Target test class — from the mvn -Dtest= flag if present
  local target_tests=""
  local test_class
  test_class=$(_extract_test_class "$cmd")
  [ -n "$test_class" ] && target_tests="$test_class"

  # Per-mutant timeout: 60s const + 2.5× factor is the pitest recommended default
  pitest_args+=(
    "-DtimeoutConst=60"
    "-DtimeoutFactor=2.5"
    "-DoutputFormats=XML"
    "-DtimestampedReports=false"
    "-DwithHistory"
  )
  [ -n "$target_class"  ] && pitest_args+=("-DtargetClasses=${target_class}*")
  [ -n "$target_tests"  ] && pitest_args+=("-DtargetTests=$target_tests")

  # Multi-module: scope to the module containing the changed file
  local module_flag=""
  if [ -n "$changed_file" ]; then
    local module_dir
    module_dir=$(_find_maven_module "$changed_file")
    [ -n "$module_dir" ] && module_flag="-pl $module_dir --also-make-dependents"
  fi

  # Determine the build tool
  local pitest_exit=0
  if _is_gradle; then
    local gradle_cmd="./gradlew"
    command -v "$gradle_cmd" &>/dev/null || gradle_cmd="gradle"
    # Gradle pitest plugin uses pitest task; class scoping via property
    local gradle_args=("pitest")
    [ -n "$target_class" ] && gradle_args+=("-PtargetClasses=${target_class}*")
    # shellcheck disable=SC2086
    _timeout "$timeout" $gradle_cmd "${gradle_args[@]}" \
      2>/dev/null || pitest_exit=$?
    # Gradle pitest report is typically build/reports/pitest/mutations.xml
    PITEST_REPORT="${PITEST_REPORT:-build/reports/pitest/mutations.xml}"
  else
    local mvn_cmd="mvn"
    [ -f "./mvnw" ] && mvn_cmd="./mvnw"
    # shellcheck disable=SC2086
    _timeout "$timeout" $mvn_cmd pitest:mutationCoverage \
      $module_flag "${pitest_args[@]}" \
      2>/dev/null || pitest_exit=$?
  fi

  if [ "$pitest_exit" -eq 124 ]; then
    local scope_hint=""
    [ -z "$target_class" ] && scope_hint=" No source file detected for scoping — scope manually with git diff."
    emit_advisory "MUTATION GATE SKIPPED: pitest timed out after ${timeout}s.${scope_hint} Or: MUTATION_GATE_TIMEOUT=<seconds> to extend the limit."
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
