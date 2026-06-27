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
# Parallelism: the independent gates run concurrently in a bounded pool capped at
# the core count (portable across Linux + macOS, no bash-4 features). Output is
# buffered per check and replayed in declared order, so the log stays readable
# and the pass/fail summary is deterministic — same "run everything, collect all
# failures" contract as the old serial runner, just faster. The bats suites also
# parallelize across files via scripts/run-bats-parallel.sh, which uses `xargs -P`
# (built into macOS + Linux) — no GNU `parallel` package required.
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

section() { printf '\n%s== %s ==%s\n' "$bold" "$1" "$reset"; }

# --- tool prerequisites (CI installs these; require them locally too) -------
missing=()
for t in shellcheck bats jq python3; do
  command -v "$t" >/dev/null 2>&1 || missing+=("$t")
done
if [ "${#missing[@]}" -gt 0 ]; then
  printf '%s%sMissing required tools: %s%s\n' "$bold" "$red" "${missing[*]}" "$reset" >&2
  printf 'Install everything the dev gates need: bash scripts/dev-setup.sh\n' >&2
  printf '  (or, macOS only: brew install %s)\n' "${missing[*]}" >&2
  exit 2
fi

# --- python module prerequisites (declared in requirements-dev.txt) ---------
# Binaries alone aren't enough: several bats suites shell out to Python scripts
# that import third-party modules. Check them up front so a missing dep fails
# loudly here instead of as a cryptic ModuleNotFoundError mid-suite.
py_missing=()
# shellcheck disable=SC2043  # single entry today; kept as a list for new modules
for m in yaml; do
  python3 -c "import $m" >/dev/null 2>&1 || py_missing+=("$m")
done
if [ "${#py_missing[@]}" -gt 0 ]; then
  printf '%s%sMissing required Python modules: %s%s\n' "$bold" "$red" "${py_missing[*]}" "$reset" >&2
  printf 'Install the dev dependencies: python3 -m pip install -r requirements-dev.txt\n' >&2
  printf '  (or run the one-shot setup: bash scripts/dev-setup.sh)\n' >&2
  exit 2
fi

# --- concurrency setup -----------------------------------------------------
# Bound the parallel pool to the online core count (portable on Linux + macOS).
JOBS="$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 2)"
case "$JOBS" in ''|*[!0-9]*) JOBS=2 ;; esac
[ "$JOBS" -ge 1 ] || JOBS=2

# bats files are fanned across cores by scripts/run-bats-parallel.sh (xargs -P),
# which needs no GNU `parallel` package — portable on every macOS + Linux box.
run_bats() { bash scripts/run-bats-parallel.sh -j "$JOBS" "$@"; }

# --- check definitions -----------------------------------------------------
# Each gate is a function returning its exit code. They are dispatched
# concurrently (bounded pool below); the dev-team content suite is split into
# tests/repo (the long pole) + the rest so the pole overlaps the other gates
# instead of running after them.

chk_shellcheck_helpers() { shellcheck -x plugins/security-assessment/scripts/*.sh; }
chk_shellcheck_tests()   { shellcheck tests/security-assessment/scripts/*.sh; }
chk_sa_shell_suite()     { bash tests/security-assessment/scripts/run-all.sh; }
chk_bats_repo()          { run_bats tests/repo/; }
chk_bats_content_rest()  { run_bats tests/knowledge/ tests/agents/ tests/commands/ tests/docs/ tests/scripts/; }
chk_model_routing() {
  run_bats \
    tests/hooks/updated_input_contract_tests.bats \
    tests/hooks/agent_model_resolve_hook_tests.bats \
    tests/hooks/model_resolve_tests.bats \
    tests/hooks/plugin_version_tests.bats
}
chk_cost_regression() { bash scripts/cost-regression-check.sh; }
chk_eval_corpus()     { python3 scripts/eval_grade.py --check-corpus; }
chk_oe_staleness()    { python3 scripts/oe_scoring_staleness.py --warn-only; }
chk_citation_lint()   { python3 scripts/citation_lint.py --all; }  # advisory (#312)
chk_skills_index()    { bash plugins/dev-team/hooks/lib/build-skills-index.sh --check; }
chk_eval_semver() {
  if [ -n "$BASE" ] && [ -n "$HEAD" ]; then
    bash scripts/eval_semver_classify.sh "$BASE" "$HEAD"
  else
    printf '%s∼ skipped (no BASE/HEAD range supplied)%s\n' "$yellow" "$reset"
  fi
}
chk_eslint() {
  if command -v npx >/dev/null 2>&1; then
    npx --no-install eslint
  else
    printf '%s∼ skipped (npx not found)%s\n' "$yellow" "$reset"
  fi
}

# Ordered list of "label::function". Order defines both the replay order and the
# summary order (declared order, independent of completion order).
CHECKS=(
  "shellcheck — security-assessment helper scripts::chk_shellcheck_helpers"
  "shellcheck — test scripts::chk_shellcheck_tests"
  "security-assessment shell test suite (run-all.sh)::chk_sa_shell_suite"
  "bats — dev-team tests/repo::chk_bats_repo"
  "bats — dev-team content (knowledge/agents/commands/docs/scripts)::chk_bats_content_rest"
  "bats — model-routing hook conformance::chk_model_routing"
  "cost-regression check::chk_cost_regression"
  "eval corpus integrity (eval_grade.py --check-corpus)::chk_eval_corpus"
  "OE scoring staleness (advisory; oe_scoring_staleness.py)::chk_oe_staleness"
  "citation drift lint (citation_lint.py, advisory)::chk_citation_lint"
  "skills catalog freshness (docs/skills.md)::chk_skills_index"
  "eval-corpus semver contract::chk_eval_semver"
  "eslint::chk_eslint"
)

# --- dispatch (bounded FIFO pool; no `wait -n`, so portable to bash 3.2) ----
RUNDIR="$(mktemp -d)"
trap 'rm -rf "$RUNDIR"' EXIT

printf '%srunning %d checks, up to %d in parallel…%s\n' "$bold" "${#CHECKS[@]}" "$JOBS" "$reset"

pids=()
idx=0
for entry in "${CHECKS[@]}"; do
  fn="${entry##*::}"
  ( "$fn" >"$RUNDIR/$idx.out" 2>&1; echo $? >"$RUNDIR/$idx.rc" ) &
  pids+=("$!")
  idx=$((idx + 1))
  # Throttle: once JOBS are in flight, block on the oldest before launching more.
  if [ "${#pids[@]}" -ge "$JOBS" ]; then
    wait "${pids[0]}" 2>/dev/null || true
    pids=("${pids[@]:1}")
  fi
done
wait  # drain the remainder

# --- aggregate in declared order -------------------------------------------
FAILURES=()
idx=0
for entry in "${CHECKS[@]}"; do
  label="${entry%%::*}"
  section "$label"
  cat "$RUNDIR/$idx.out" 2>/dev/null || true
  rc="$(cat "$RUNDIR/$idx.rc" 2>/dev/null || echo 1)"
  if [ "$rc" = "0" ]; then
    printf '%s✓ %s%s\n' "$green" "$label" "$reset"
  else
    printf '%s✗ %s%s\n' "$red" "$label" "$reset"
    FAILURES+=("$label")
  fi
  idx=$((idx + 1))
done

# --- summary ---------------------------------------------------------------
section "summary"
if [ "${#FAILURES[@]}" -eq 0 ]; then
  printf '%s%sAll local CI checks passed.%s\n' "$bold" "$green" "$reset"
  exit 0
fi
printf '%s%s%d check(s) failed:%s\n' "$bold" "$red" "${#FAILURES[@]}" "$reset" >&2
for f in "${FAILURES[@]}"; do printf '  %s✗ %s%s\n' "$red" "$f" "$reset" >&2; done
exit 1
