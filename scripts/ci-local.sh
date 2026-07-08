#!/usr/bin/env bash
# ci-local.sh — run the same deterministic checks GitHub CI runs, locally.
#
# Mirrors the free/hermetic jobs in .github/workflows/plugin-tests.yml and the
# structural + semver gates in .github/workflows/agent-eval.yml. The paid live
# agent-eval is NOT here — it is opt-in and lives in scripts/eval-changed.sh.
#
# Usage:
#   bash scripts/ci-local.sh [--changed-only] [BASE HEAD]
#
# BASE/HEAD (optional) enable the eval-corpus semver-contract check, which needs
# a commit range (the pre-push hook passes the push range). Without them that one
# check is skipped; everything else always runs.
#
# --changed-only (optional, developer convenience) skips any suite whose watched
# paths have no changed files in `git diff`, logging each skip. It is NEVER the
# default and the pre-push hook does not pass it. The changed-file set is the
# BASE..HEAD range when supplied, otherwise the working tree vs HEAD plus
# untracked files. If `git diff` fails or the set is empty, all suites run.
#
# Parallelism: the independent gates run concurrently in a bounded pool capped at
# the core count (portable across Linux + macOS, no bash-4 features). Output is
# buffered per check and replayed in declared order, so the log stays readable
# and the pass/fail summary is deterministic — same "run everything, collect all
# failures" contract as the old serial runner, just faster.
#
# Exit codes: 0 = all checks passed, 1 = one or more failed, 2 = missing tool.

set -uo pipefail

# --- git env scrub (issue #546) -------------------------------------------
# Git exports GIT_DIR / GIT_INDEX_FILE / GIT_WORK_TREE / GIT_PREFIX /
# GIT_REFLOG_ACTION into the pre-push hook's environment. Left in place,
# fixture tests that run `git init` / `git commit` / `git push` inherit
# them and target the parent worktree's gitdir instead of their tempdirs,
# silently rewriting refs/heads/*. Scrub at the boundary so no child
# process can see them.
unset GIT_DIR GIT_INDEX_FILE GIT_WORK_TREE GIT_PREFIX GIT_REFLOG_ACTION

# CI_LOCAL_PROBE_ENV=1 short-circuits ci-local to report the state of the
# five scrubbed vars and exit 0. Used by tests/scripts/test_ci_local_hermetic.py
# to assert the scrub happened without running the full suite. Deliberately
# NARROW — only reports the exact names the unset targeted so the probe
# cannot exfiltrate unrelated GIT_* secrets (GIT_HTTP_EXTRAHEADER carries
# bearer tokens, GIT_ASKPASS carries credential-helper paths, etc.).
if [ "${CI_LOCAL_PROBE_ENV:-}" = "1" ]; then
  for _v in GIT_DIR GIT_INDEX_FILE GIT_WORK_TREE GIT_PREFIX GIT_REFLOG_ACTION; do
    eval "_val=\${$_v-__unset__}"
    printf '%s=%s\n' "$_v" "$_val"
  done
  exit 0
fi

cd "$(git rev-parse --show-toplevel)" || exit 2

# --- argument parsing ------------------------------------------------------
# --changed-only is a position-independent flag; BASE/HEAD are positional and
# keep their existing meaning so the pre-push hook's `ci-local.sh BASE HEAD`
# invocation is unaffected.
CHANGED_ONLY=0
# --only=fn[,fn...] runs just the named checks. CI calls it so each gate job
# invokes the same definitions this script owns (single source of truth),
# keeping the required-status-check job names stable. The per-job tool installs
# live in the workflow, so the global prereq gate below is skipped under --only.
ONLY=""
positional=()
for arg in "$@"; do
  case "$arg" in
    --changed-only) CHANGED_ONLY=1 ;;
    --only=*) ONLY="${arg#--only=}" ;;
    *) positional+=("$arg") ;;
  esac
done
set -- ${positional[@]+"${positional[@]}"}

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
# Skipped under --only: CI invokes a subset and installs exactly that subset's
# tools per job, so a full-toolchain gate here would false-fail those jobs.
if [ -z "$ONLY" ]; then
  missing=()
  for t in shellcheck jq python3 semgrep; do
    command -v "$t" >/dev/null 2>&1 || missing+=("$t")
  done
  if [ "${#missing[@]}" -gt 0 ]; then
    printf '%s%sMissing required tools: %s%s\n' "$bold" "$red" "${missing[*]}" "$reset" >&2
    printf 'Install everything the dev gates need: bash scripts/dev-setup.sh\n' >&2
    printf '  (or, macOS only: brew install %s)\n' "${missing[*]}" >&2
    exit 2
  fi

  # --- python module prerequisites (declared in requirements-dev.txt) -------
  # Binaries alone aren't enough: several gates shell out to Python scripts that
  # import third-party modules. Check them up front so a missing dep fails
  # loudly here instead of as a cryptic ModuleNotFoundError mid-suite.
  py_missing=()
  for m in yaml httpx; do
    python3 -c "import $m" >/dev/null 2>&1 || py_missing+=("$m")
  done
  if [ "${#py_missing[@]}" -gt 0 ]; then
    printf '%s%sMissing required Python modules: %s%s\n' "$bold" "$red" "${py_missing[*]}" "$reset" >&2
    printf 'Install the dev dependencies: python3 -m pip install -r requirements-dev.txt\n' >&2
    printf '  (or run the one-shot setup: bash scripts/dev-setup.sh)\n' >&2
    exit 2
  fi
fi

# --- concurrency setup -----------------------------------------------------
# Bound the parallel pool to the online core count (portable on Linux + macOS).
JOBS="$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 2)"
case "$JOBS" in ''|*[!0-9]*) JOBS=2 ;; esac
[ "$JOBS" -ge 1 ] || JOBS=2

# --- --changed-only resolution ---------------------------------------------
# Source the suite->path mapping + matcher (pure logic, unit-tested separately),
# then resolve the changed-file set once. Any failure or an empty set disables
# the flag so all suites run — the safe direction.
CHANGED_LIST=""
if [ "$CHANGED_ONLY" = "1" ]; then
  # shellcheck source=scripts/lib/ci-changed-only.sh
  . scripts/lib/ci-changed-only.sh
  # The trailing `--` ends option parsing so a BASE/HEAD value beginning with
  # `-` can't be misread as a git flag (defense-in-depth; matches the sibling
  # eval_semver_classify.sh).
  get_changed_files() {
    if [ -n "$BASE" ] && [ -n "$HEAD" ]; then
      git diff --name-only "$BASE" "$HEAD" --
    else
      git diff --name-only HEAD -- || return 1
      git ls-files --others --exclude-standard
    fi
  }
  # Guard: any failure or an empty changeset disables the flag so all suites run.
  if ! CHANGED_LIST="$(get_changed_files 2>/dev/null)" || [ -z "$CHANGED_LIST" ]; then
    printf '%s∼ --changed-only: no usable git diff (failed or empty) — running all suites%s\n' \
      "$yellow" "$reset"
    CHANGED_ONLY=0
  fi
fi

# --- check definitions -----------------------------------------------------
# Each gate is a function returning its exit code. They are dispatched
# concurrently (bounded pool below); the dev-team content suite is split into
# tests/repo (the long pole) + the rest so the pole overlaps the other gates
# instead of running after them.

chk_shellcheck_helpers() { shellcheck -x plugins/security-assessment/scripts/*.sh; }
chk_shellcheck_tests()   { shellcheck tests/security-assessment/scripts/*.sh scripts/audit-rules-vs-prompts.sh; }
chk_sa_shell_suite()     { bash tests/security-assessment/scripts/run-all.sh; }
# chk_model_routing (formerly ran 4 bats files) — retired in #618. The bash
# hooks under test have been ported to Python (#585 / #577 / #609), and their
# unit tests now live in plugins/dev-team/tests/hooks/test_*.py (invoked via
# chk_hook_units below).
chk_cost_regression() { bash scripts/cost-regression-check.sh; }
chk_eval_corpus()     { python3 scripts/eval_grade.py --check-corpus; }
chk_oe_staleness()    { python3 scripts/oe_scoring_staleness.py --warn-only; }
chk_citation_lint()   { python3 scripts/citation_lint.py --all; }  # advisory (#312)
chk_md_references()   { python3 scripts/check_md_references.py; }
chk_skills_index() {
  local script=plugins/dev-team/hooks/lib/build_skills_index.py
  python3 "$script" --check || return 1
  for plugin_dir in plugins/security-assessment plugins/marketplace-dev; do
    python3 "$script" --plugin-dir "$plugin_dir" --check || return 1
  done
}
chk_rules_vs_prompts() { bash scripts/audit-rules-vs-prompts.sh; }
chk_python_only() {
  if [ -n "$BASE" ]; then
    python3 scripts/check-python-only.py --base "$BASE"
  else
    python3 scripts/check-python-only.py  # defaults to origin/main, blocking
  fi
}
chk_semgrep_fixtures() { python3 scripts/audit-semgrep-fixtures.py; }
chk_harness_smoke()    { python3 tests/security-assessment/harness/smoke_test.py; }
chk_harness_scope()    { python3 tests/security-assessment/harness/scope_enforcement_test.py; }
# Lightweight nav gate: assemble the docs tree, then assert every mkdocs nav
# entry resolves to a file (the breakage a deleted/renamed doc leaves behind).
# The full mkdocs build + lychee body-link scan stay CI-only (link-check.yml) so
# mkdocs/lychee never become local prereqs.
chk_nav_integrity() {
  bash scripts/assemble-docs.sh >/dev/null 2>&1 || return 1
  python3 scripts/check_nav_integrity.py
}
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
# plugins/dev-team/tests/hooks/parity/ (the .sh↔.py parity harness) was retired
# in #618 (epic #572) once every shipped hook + script became Python-only. The
# going-forward coverage lives in plugins/dev-team/tests/hooks/test_*.py and
# tests/repo/test_*.py (pytest, both invoked here via chk_hook_units). Every
# content-guard *.bats fixture suite has now been ported to pytest (epic
# #668) and bats-core itself is retired (#677) — chk_hook_units is the sole
# content-guard gate; there is no separate bats check left to fold in.
chk_hook_units() {
  if ! python3 -c 'import pytest' >/dev/null 2>&1; then
    printf '%s∼ skipped (pytest not installed — see requirements-dev.txt)%s\n' "$yellow" "$reset"
    return 0
  fi
  # tests/agents/, tests/commands/, tests/docs/, tests/knowledge/, and
  # tests/bats/ were ported from bats to pytest under issue #675 (epic
  # #668). tests/repo/'s eval/cost/telemetry/workflow-audit suites were
  # ported under #672 (epic #668) and already ran here. tests/skills/ was
  # ported under issue #674. tests/scripts/ was ported under issue #676 and
  # is folded in here for the first time by #677 (its former bats runner,
  # chk_bats_content_rest, retired with bats-core itself) — excluding the
  # csharp_stryker_net_* wrapper tests, which stay on their own dedicated
  # Windows workflow (wrapper-windows.yml) because they are timing/signal
  # sensitive and not portable to this runner, matching the pre-existing
  # tests/hooks/ exclusion below.
  # This suite is the wall-clock long pole. Parallelize it across cores when
  # pytest-xdist is installed (declared in requirements-dev.txt); fall back to a
  # serial run when it is absent so the gate never hard-depends on xdist.
  # --dist loadfile keeps every test from one file on a single worker, preserving
  # intra-file execution order — the git-subprocess suites (e.g. progress_guardian)
  # are order-sensitive and race when their tests are split across workers.
  parallel=()
  if python3 -c 'import xdist' >/dev/null 2>&1; then
    parallel=(-n auto --dist loadfile)
  fi
  python3 -m pytest plugins/dev-team/tests tests/repo tests/agents tests/commands \
    tests/docs tests/knowledge tests/bats tests/skills tests/scripts \
    --ignore=tests/scripts/test_csharp_stryker_net_wrapper.py \
    --ignore=tests/scripts/test_csharp_stryker_net_status_loop.py \
    ${parallel[@]+"${parallel[@]}"}
}

# Ordered list of "label::function". Order defines both the replay order and the
# summary order (declared order, independent of completion order).
CHECKS=(
  "shellcheck — security-assessment helper scripts::chk_shellcheck_helpers"
  "shellcheck — test scripts::chk_shellcheck_tests"
  "security-assessment shell test suite (run-all.sh)::chk_sa_shell_suite"
  "cost-regression check::chk_cost_regression"
  "semgrep rule fixtures (audit-semgrep-fixtures.py)::chk_semgrep_fixtures"
  "red-team harness smoke (smoke_test.py)::chk_harness_smoke"
  "red-team harness scope enforcement (scope_enforcement_test.py)::chk_harness_scope"
  "rules-vs-prompts audit (audit-rules-vs-prompts.sh)::chk_rules_vs_prompts"
  "prefer-Python-over-bash audit (check-python-only.py)::chk_python_only"
  "eval corpus integrity (eval_grade.py --check-corpus)::chk_eval_corpus"
  "OE scoring staleness (advisory; oe_scoring_staleness.py)::chk_oe_staleness"
  "citation drift lint (citation_lint.py, advisory)::chk_citation_lint"
  "markdown reference integrity (check_md_references.py)::chk_md_references"
  "skills catalog freshness (docs/skills.md)::chk_skills_index"
  "nav integrity (mkdocs nav → assembled file)::chk_nav_integrity"
  "eval-corpus semver contract::chk_eval_semver"
  "eslint::chk_eslint"
  "plugin hook + script unit tests (pytest plugins/dev-team/tests)::chk_hook_units"
)

# --only=fn[,fn...] : keep just the named checks (CI invokes per-job subsets).
if [ -n "$ONLY" ]; then
  filtered=()
  for entry in ${CHECKS[@]+"${CHECKS[@]}"}; do
    fn="${entry##*::}"
    case ",$ONLY," in *",$fn,"*) filtered+=("$entry") ;; esac
  done
  if [ "${#filtered[@]}" -eq 0 ]; then
    printf '%s%sNo checks matched --only=%s%s\n' "$bold" "$red" "$ONLY" "$reset" >&2
    exit 2
  fi
  CHECKS=(${filtered[@]+"${filtered[@]}"})
fi

# --- dispatch (bounded FIFO pool; no `wait -n`, so portable to bash 3.2) ----
RUNDIR="$(mktemp -d)"
trap 'rm -rf "$RUNDIR"' EXIT

printf '%srunning %d checks, up to %d in parallel…%s\n' "$bold" "${#CHECKS[@]}" "$JOBS" "$reset"

pids=()
idx=0
for entry in "${CHECKS[@]}"; do
  fn="${entry##*::}"
  # --changed-only: skip suites whose watched paths saw no change. Record the
  # skip as a passing result so the aggregation below logs it in declared order.
  if [ "$CHANGED_ONLY" = "1" ] && ! ci_suite_has_changes "$fn" "$CHANGED_LIST"; then
    printf '%s∼ skipped (no relevant changes)%s\n' "$yellow" "$reset" >"$RUNDIR/$idx.out"
    echo 0 >"$RUNDIR/$idx.rc"
    idx=$((idx + 1))
    continue
  fi
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
