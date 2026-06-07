#!/usr/bin/env bash
# ci-local.sh — run the same deterministic checks GitHub CI runs, locally.
#
# Mirrors the free/hermetic jobs in .github/workflows/plugin-tests.yml and the
# structural + semver gates in .github/workflows/agent-eval.yml. The paid live
# agent-eval is NOT here — it is opt-in and lives in scripts/eval-changed.sh.
#
# Usage:
#   bash scripts/ci-local.sh [BASE HEAD]
#
# BASE/HEAD (optional) enable the eval-corpus semver-contract check, which needs
# a commit range (the pre-push hook passes the push range). Without them that one
# check is skipped; everything else always runs.
#
# Exit codes: 0 = all checks passed, 1 = one or more failed, 2 = missing tool.

set -uo pipefail

cd "$(git rev-parse --show-toplevel)" || exit 2

BASE="${1:-}"
HEAD="${2:-}"

# --- output helpers --------------------------------------------------------
bold=$(tput bold 2>/dev/null || true)
red=$(tput setaf 1 2>/dev/null || true)
green=$(tput setaf 2 2>/dev/null || true)
yellow=$(tput setaf 3 2>/dev/null || true)
reset=$(tput sgr0 2>/dev/null || true)

FAILURES=()

section() { printf '\n%s== %s ==%s\n' "$bold" "$1" "$reset"; }

# run <label> <command...> — run a check, record failure, keep going.
run() {
  local label="$1"; shift
  section "$label"
  if "$@"; then
    printf '%s✓ %s%s\n' "$green" "$label" "$reset"
  else
    printf '%s✗ %s%s\n' "$red" "$label" "$reset"
    FAILURES+=("$label")
  fi
}

# --- tool prerequisites (CI installs these; require them locally too) -------
missing=()
for t in shellcheck bats jq python3; do
  command -v "$t" >/dev/null 2>&1 || missing+=("$t")
done
if [ "${#missing[@]}" -gt 0 ]; then
  printf '%s%sMissing required tools: %s%s\n' "$bold" "$red" "${missing[*]}" "$reset" >&2
  printf 'Install them (macOS): brew install %s\n' "${missing[*]}" >&2
  exit 2
fi

# --- plugin-tests.yml :: shell-tests --------------------------------------
run "shellcheck — security-assessment helper scripts" \
  shellcheck -x plugins/security-assessment/scripts/*.sh

run "shellcheck — test scripts" \
  bash -c 'shellcheck plugins/security-assessment/tests/scripts/*.sh'

run "security-assessment shell test suite (run-all.sh)" \
  bash plugins/security-assessment/tests/scripts/run-all.sh

# --- plugin-tests.yml :: bats-tests ---------------------------------------
run "bats — dev-team content suites" \
  bats tests/repo/ tests/knowledge/ tests/agents/ tests/commands/ tests/docs/

run "bats — model-routing hook conformance" \
  bats \
    tests/hooks/updated_input_contract_tests.bats \
    tests/hooks/agent_model_resolve_hook_tests.bats \
    tests/hooks/model_resolve_tests.bats

# --- plugin-tests.yml :: cost-regression gate (#140) -----------------------
run "cost-regression check" \
  bash scripts/cost-regression-check.sh

# --- agent-eval.yml :: structural gate (model-free) ------------------------
# (eval_grader_tests.bats already ran above as part of tests/repo/.)
run "eval corpus integrity (eval_grade.py --check-corpus)" \
  python3 scripts/eval_grade.py --check-corpus

# --- agent-eval.yml :: semver contract (needs a commit range) --------------
if [ -n "$BASE" ] && [ -n "$HEAD" ]; then
  run "eval-corpus semver contract" \
    bash scripts/eval_semver_classify.sh "$BASE" "$HEAD"
else
  section "eval-corpus semver contract"
  printf '%s∼ skipped (no BASE/HEAD range supplied)%s\n' "$yellow" "$reset"
fi

# --- ESLint (not yet a CI job; lints the clean TS fixtures + first-party JS)-
if command -v npx >/dev/null 2>&1; then
  run "eslint" npx --no-install eslint
else
  section "eslint"
  printf '%s∼ skipped (npx not found)%s\n' "$yellow" "$reset"
fi

# --- summary ---------------------------------------------------------------
section "summary"
if [ "${#FAILURES[@]}" -eq 0 ]; then
  printf '%s%sAll local CI checks passed.%s\n' "$bold" "$green" "$reset"
  exit 0
fi
printf '%s%s%d check(s) failed:%s\n' "$bold" "$red" "${#FAILURES[@]}" "$reset" >&2
for f in "${FAILURES[@]}"; do printf '  %s✗ %s%s\n' "$red" "$f" "$reset" >&2; done
exit 1
