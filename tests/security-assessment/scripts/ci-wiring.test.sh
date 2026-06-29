#!/usr/bin/env bash
# ci-wiring.test.sh — asserts the plugin-tests CI workflow is wired up
# and invokes both run-all.sh and shellcheck on the helper scripts.

set -uo pipefail

THIS_DIR="$(cd "$(dirname "$0")" && pwd)"
# Repo root is three levels up from tests/security-assessment/scripts/:
#   tests/security-assessment/scripts → tests/security-assessment → tests → <repo>
REPO_ROOT="$(cd "$THIS_DIR/../../.." && pwd)"
WORKFLOW="$REPO_ROOT/.github/workflows/plugin-tests.yml"

FAILED=0
fail() { echo "  FAIL: $*" >&2; FAILED=$((FAILED+1)); }
ok()   { echo "  PASS: $*"; }

test_workflow_exists() {
  [[ -f "$WORKFLOW" ]] || { fail "workflow not found at $WORKFLOW"; return; }
  ok "workflow file exists at .github/workflows/plugin-tests.yml"
}

test_workflow_runs_tests() {
  [[ -f "$WORKFLOW" ]] || { fail "workflow missing; prerequisite"; return; }
  # The suite runs either directly or through the shared local gate
  # (scripts/ci-local.sh's chk_sa_shell_suite — single source of truth for CI
  # and pre-push). Accept either wiring, but for the indirect form confirm the
  # ci-local check actually reaches run-all.sh so the assertion stays real.
  local cilocal="$REPO_ROOT/scripts/ci-local.sh"
  if grep -q 'tests/security-assessment/scripts/run-all.sh' "$WORKFLOW"; then
    ok "workflow invokes tests/security-assessment/scripts/run-all.sh"
  elif grep -q 'chk_sa_shell_suite' "$WORKFLOW" \
       && grep -q 'chk_sa_shell_suite.*run-all.sh' "$cilocal"; then
    ok "workflow invokes run-all.sh via ci-local (chk_sa_shell_suite)"
  else
    fail "workflow does not invoke run-all.sh (directly or via ci-local chk_sa_shell_suite)"
  fi
}

test_workflow_runs_shellcheck() {
  [[ -f "$WORKFLOW" ]] || { fail "workflow missing; prerequisite"; return; }
  # Accept any reference to shellcheck — a `run: shellcheck ...` step, a
  # named step, or a `uses:` action — without depending on fragile
  # layout assumptions about newlines or leading whitespace.
  grep -qE 'shellcheck' "$WORKFLOW" \
    || { fail "workflow does not mention shellcheck at all"; return; }
  ok "workflow runs shellcheck"
}

test_workflow_targets_pr_events() {
  [[ -f "$WORKFLOW" ]] || { fail "workflow missing; prerequisite"; return; }
  grep -q 'pull_request' "$WORKFLOW" \
    || { fail "workflow does not trigger on pull_request events"; return; }
  ok "workflow triggers on pull_request"
}

echo "=== ci-wiring tests ==="
test_workflow_exists
test_workflow_runs_tests
test_workflow_runs_shellcheck
test_workflow_targets_pr_events

if [[ $FAILED -gt 0 ]]; then
  echo "=== FAILED: $FAILED test(s) ==="
  exit 1
fi
echo "=== all ci-wiring tests passed ==="
exit 0
