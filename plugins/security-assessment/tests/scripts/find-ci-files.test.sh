#!/usr/bin/env bash
# find-ci-files.test.sh — tests for scripts/find-ci-files.sh.
#
# Builds the fixture tree in $TMP at runtime rather than committing it —
# avoids the commit hazards of nested .git/ dirs and gitignored
# node_modules/. Also keeps the tests fully self-contained.

set -uo pipefail

THIS_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$THIS_DIR/../../scripts/find-ci-files.sh"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

FAILED=0
fail() { echo "  FAIL: $*" >&2; FAILED=$((FAILED+1)); }
ok()   { echo "  PASS: $*"; }

# --- build_positive_fixture -----------------------------------------------
# Both .yml and .yaml variants for azure-pipelines and .github/workflows,
# plus a .groovy file under each of ci/ and jenkins/ to exercise the
# groovy-scope positive case.
build_positive_fixture() {
  local root="$1"
  mkdir -p "$root/ci" "$root/jenkins" "$root/.github/workflows"
  touch "$root/Jenkinsfile"
  touch "$root/ci/build.groovy"
  touch "$root/jenkins/deploy.groovy"
  touch "$root/azure-pipelines.yml"
  touch "$root/azure-pipelines-release.yaml"
  touch "$root/.github/workflows/ci.yml"
  touch "$root/.github/workflows/release.yaml"
  touch "$root/.gitlab-ci.yml"
  touch "$root/bitbucket-pipelines.yml"
  touch "$root/Dockerfile"
}

# --- build_excluded_fixture -----------------------------------------------
# Every match type seeded under every excluded root so that a pruning
# regression on a single root leaks at least one file.
build_excluded_fixture() {
  local root="$1"
  local excluded_root
  for excluded_root in node_modules vendor .git bin obj; do
    mkdir -p "$root/$excluded_root/ci" \
             "$root/$excluded_root/jenkins" \
             "$root/$excluded_root/.github/workflows"
    touch "$root/$excluded_root/Jenkinsfile"
    touch "$root/$excluded_root/Dockerfile"
    touch "$root/$excluded_root/.gitlab-ci.yml"
    touch "$root/$excluded_root/bitbucket-pipelines.yml"
    touch "$root/$excluded_root/azure-pipelines.yml"
    touch "$root/$excluded_root/azure-pipelines.yaml"
    touch "$root/$excluded_root/.github/workflows/ci.yml"
    touch "$root/$excluded_root/.github/workflows/ci.yaml"
    touch "$root/$excluded_root/ci/build.groovy"
    touch "$root/$excluded_root/jenkins/deploy.groovy"
  done
}

# --- 1. -h prints usage, match patterns, excluded roots, exit-code contract
test_help() {
  local out err rc
  out="$(bash "$SCRIPT" -h 2>"$TMP/help_err")" && rc=0 || rc=$?
  err="$(cat "$TMP/help_err")"
  [[ $rc -eq 0 ]] || { fail "-h exited non-zero"; return; }
  [[ -z "$err" ]] || { fail "-h wrote to stderr: $err"; return; }
  grep -q 'usage:' <<<"$out" || { fail "-h missing 'usage:'"; return; }
  # Match patterns advertised
  for pat in Jenkinsfile azure-pipelines 'gitlab-ci' bitbucket-pipelines Dockerfile groovy; do
    grep -q -i "$pat" <<<"$out" || { fail "-h missing match pattern '$pat'"; return; }
  done
  # Excluded roots advertised
  for root in node_modules vendor '\.git' bin obj; do
    grep -q -E "$root" <<<"$out" || { fail "-h missing excluded root '$root'"; return; }
  done
  # Exit-code contract
  for code in 0 1 2 3; do
    grep -q -E "(^|[^0-9])${code}([^0-9]|$)" <<<"$out" || { fail "-h missing exit code $code"; return; }
  done
  ok "-h prints match patterns, excluded roots, exit-code contract"
}

# --- 2. Missing target-dir argument → non-zero + usage to stderr ----------
test_missing_arg() {
  local rc err
  err="$(bash "$SCRIPT" 2>&1 >/dev/null)" && rc=0 || rc=$?
  [[ $rc -ne 0 ]] || { fail "no-args exited 0"; return; }
  grep -q 'usage:' <<<"$err" || { fail "no-args missing usage on stderr"; return; }
  ok "missing-arg: non-zero exit + usage on stderr"
}

# --- 3. Non-existent target directory → non-zero + actionable stderr ------
test_nonexistent_target() {
  local rc err
  err="$(bash "$SCRIPT" "$TMP/does-not-exist" 2>&1 >/dev/null)" && rc=0 || rc=$?
  [[ $rc -ne 0 ]] || { fail "nonexistent-dir exited 0"; return; }
  grep -qi 'target directory not found' <<<"$err" \
    || { fail "stderr missing 'target directory not found': $err"; return; }
  ok "nonexistent target: non-zero + actionable stderr"
}

# --- 4. Positive fixture: all file types (.yml AND .yaml), ci/ AND jenkins/ --
test_positive_fixture() {
  local root="$TMP/positive"
  build_positive_fixture "$root"
  local out
  out="$(bash "$SCRIPT" "$root")"
  local expected
  expected="$(printf '%s\n' \
    "$root/.github/workflows/ci.yml" \
    "$root/.github/workflows/release.yaml" \
    "$root/.gitlab-ci.yml" \
    "$root/Dockerfile" \
    "$root/Jenkinsfile" \
    "$root/azure-pipelines-release.yaml" \
    "$root/azure-pipelines.yml" \
    "$root/bitbucket-pipelines.yml" \
    "$root/ci/build.groovy" \
    "$root/jenkins/deploy.groovy" | sort)"
  if [[ "$out" != "$expected" ]]; then
    fail "positive fixture output mismatch"
    echo "--- expected ---" >&2; echo "$expected" >&2
    echo "--- got ---" >&2;      echo "$out" >&2
    return
  fi
  ok "positive fixture: 10 files incl. .yaml variants and ci/+jenkins/ groovy"
}

# --- 5. Excluded fixture: excluded roots produce no output ----------------
test_excluded_fixture() {
  local root="$TMP/excluded"
  build_excluded_fixture "$root"
  local out
  out="$(bash "$SCRIPT" "$root")"
  if [[ -n "$out" ]]; then
    fail "excluded fixture produced output: $out"
    return
  fi
  ok "excluded fixture: node_modules/vendor/.git/bin/obj all skipped"
}

# --- 6. Empty target: no output, exit 0 -----------------------------------
test_empty_target() {
  local root="$TMP/empty"
  mkdir -p "$root"
  local rc out
  out="$(bash "$SCRIPT" "$root")" && rc=0 || rc=$?
  [[ $rc -eq 0 ]] || { fail "empty-target exited non-zero"; return; }
  [[ -z "$out" ]] || { fail "empty-target produced output: $out"; return; }
  ok "empty target: no output, exit 0"
}

# --- 7. Groovy matches only under ci/ or jenkins/ subtrees ---------------
# Positive + negative: jenkins/build.groovy MUST be matched; src/build.groovy
# MUST NOT. Guards against the groovy rule being deleted outright.
test_groovy_scope() {
  local root="$TMP/groovy-scope"
  mkdir -p "$root/src" "$root/jenkins"
  touch "$root/src/build.groovy"        # negative — must not match
  touch "$root/jenkins/deploy.groovy"    # positive — must match
  local out
  out="$(bash "$SCRIPT" "$root")"
  grep -qxF "$root/jenkins/deploy.groovy" <<<"$out" \
    || { fail "groovy in jenkins/ not matched: $out"; return; }
  if grep -qxF "$root/src/build.groovy" <<<"$out"; then
    fail "rogue groovy in src/ was matched: $out"
    return
  fi
  ok "groovy matches jenkins/ (positive) + skips src/ (negative)"
}

echo "=== find-ci-files tests ==="
test_help
test_missing_arg
test_nonexistent_target
test_positive_fixture
test_excluded_fixture
test_empty_target
test_groovy_scope

if [[ $FAILED -gt 0 ]]; then
  echo "=== FAILED: $FAILED test(s) ==="
  exit 1
fi
echo "=== all find-ci-files tests passed ==="
exit 0
