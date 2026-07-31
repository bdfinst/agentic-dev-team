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
  for t in shellcheck jq python3 semgrep ruff; do
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

# --- timing helper (opt-in per-step timing; pure renderer, sourced) ---------
# shellcheck source=scripts/lib/ci-timing.sh
. scripts/lib/ci-timing.sh

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
chk_sa_mcp_tools()    { python3 plugins/dev-team/scripts/check_security_assessment_mcp_tools.py; }
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
# ADR 0014 puts shipped plugin code on Python 3.8. This check proves it by
# asking a real 3.8 interpreter, never by pattern-matching source for
# "APIs newer than 3.8" — the first version of this gate was exactly such a
# denylist, and it reported the shipped tree clean while hooks/lib/cost_meter.py
# used PEP 584's `dict | dict`, which 3.8 rejects.
#
# Byte-compile catches syntax; the import probe catches evaluation (a PEP 585
# generic in a module-level type alias compiles everywhere and raises on 3.8).
# Running the shipped suite on 3.8 is the strong form and belongs in CI, where
# provisioning an interpreter plus test deps is free; see the note in
# tests/repo/test_python_floor.py.
#
# Fails — never skips — when no 3.8 can be obtained. A gate that quietly
# downgrades to "skipped" on the machines least likely to have the floor
# interpreter is the failure mode this whole check exists to prevent.
_resolve_python38() {
  if command -v python3.8 >/dev/null 2>&1; then
    command -v python3.8
    return 0
  fi
  if command -v uv >/dev/null 2>&1; then
    uv python find 3.8 2>/dev/null && return 0
    uv python install 3.8 >/dev/null 2>&1 && uv python find 3.8 2>/dev/null && return 0
  fi
  return 1
}

chk_python_floor() {
  local py38
  if ! py38="$(_resolve_python38)" || [ -z "$py38" ]; then
    printf 'No Python 3.8 interpreter available, and this gate does not skip.\n' >&2
    printf 'Install one:  uv python install 3.8   (or apt/brew a python3.8)\n' >&2
    printf 'ADR 0014 sets the shipped floor at 3.8; see tests/repo/test_python_floor.py.\n' >&2
    return 1
  fi
  printf 'floor interpreter: %s (%s)\n' "$py38" "$("$py38" -V 2>&1)"

  find plugins/dev-team -name '*.py' \
    -not -path '*/tests/*' \
    -not -path '*rule-fixtures*' \
    -print0 | xargs -0 -n1 "$py38" -m py_compile || return 1

  "$py38" scripts/import_probe_shipped.py
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
# Python lint (ruff.toml at repo root excludes fixture/eval-corpus snippet
# dirs — see that file's header comment for why). Same tool /code-review and
# /build's self-heal dispatch on Python files (plugins/dev-team/skills/
# static-analysis-integration/SKILL.md); this gate keeps the repo's own
# Python at the bar those skills hold contributor changes to.
chk_ruff() { ruff check .; }
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
  # sensitive and not portable to this runner.
  # tests/hooks/ (repo-root, distinct from plugins/dev-team/tests/hooks/)
  # joined this list in #1475: it used to be excluded on the belief its
  # suites needed stryker/pitest or were timing-based. Neither is true of
  # this directory's own *.py test files — the stryker/pitest/mutmut ADAPTER
  # tests that actually shell out to those tools live in
  # plugins/dev-team/tests/hooks/ (already covered by `plugins/dev-team/tests`
  # below); this directory's tests only read static fixture files it hosts at
  # tests/hooks/fixtures/ + tests/hooks/fake-bin/ (consumed cross-tree by
  # plugins/dev-team/tests/hooks/test_mutation_adapters_lib.py), never invoke
  # a real stryker/pitest binary. Repo-root tests/hooks/ is fast,
  # deterministic, and portable. Its exclusion let two hooks.json dispatch-
  # matcher regressions from ADR 0026's retirement of
  # hooks/agent_model_resolve.py go silently red for a full migration.
  # This suite is the wall-clock long pole. Parallelize it across cores when
  # pytest-xdist is installed (declared in requirements-dev.txt); fall back to a
  # serial run when it is absent so the gate never hard-depends on xdist.
  # --dist loadfile keeps every test from one file on a single worker, preserving
  # intra-file execution order — the git-subprocess suites (e.g. progress_guardian)
  # are order-sensitive and race when their tests are split across workers.
  # Worker count (#1129): `-n auto` spawns one worker per core. In a FULL local
  # run (no --only) this check is dispatched inside ci-local.sh's outer parallel
  # pool alongside ~17 other checks, so `auto` oversubscribes every core and
  # starves the co-runners — eslint measured 2.3s solo but 34.7s here while
  # pytest's workers held the cores. This suite is coordination-bound (~2.7 cores
  # of real work even at -n auto), so leaving ~1/3 of the cores for the pool
  # barely moves its own wall-clock while letting the light co-runners finish in
  # the freed headroom. Under --only (CI shards each gate into its own job) pytest
  # is effectively the sole heavy check, so keep -n auto there — no co-runners to
  # protect, and small CI runners want every core.
  parallel=()
  if python3 -c 'import xdist' >/dev/null 2>&1; then
    local workers="auto"
    if [ -z "$ONLY" ]; then
      local cores
      cores="$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)"
      case "$cores" in '' | *[!0-9]*) cores=4 ;; esac
      workers=$(( cores - cores / 3 ))
      [ "$workers" -ge 2 ] || workers=2
    fi
    # loadgroup is a strict superset of loadfile: ungrouped tests still get
    # file-level grouping, but tests carrying an explicit xdist_group mark
    # (e.g. "careful-state-shared-file", test-improve issue-1354 Story 6)
    # are additionally forced onto the SAME worker even across different
    # files — closing a real, observed flakiness source: several test files
    # write to hooks/careful-state.json, a fixed real path (not
    # tmp_path-isolated by design — see those files' own docstrings), and
    # loadfile alone doesn't stop two DIFFERENT files' tests from racing on
    # it when scheduled to different workers concurrently.
    parallel=(-n "$workers" --dist loadgroup)
  fi
  python3 -m pytest plugins/dev-team/tests tests/repo tests/agents tests/commands \
    tests/docs tests/knowledge tests/bats tests/skills tests/scripts tests/hooks \
    --ignore=tests/scripts/test_csharp_stryker_net_wrapper.py \
    --ignore=tests/scripts/test_csharp_stryker_net_status_loop.py \
    ${parallel[@]+"${parallel[@]}"}
}
# Informational coverage report over the plugin's own source (.coveragerc) —
# a SEPARATE, SERIAL run, deliberately not folded into chk_hook_units above.
# Sharing chk_hook_units's parallel run with an informational, always-slower
# --cov pass was the wrong design regardless of cause: determinism (a hard
# quality target) on the gate every push depends on outranks this report's
# own wall-clock (test-improve issue-1354, Story 1). Always exits 0 —
# informational only, and a coverage-run-only failure (extremely unlikely,
# since it's the same tests) is logged, not gated.
chk_coverage_report() {
  if ! python3 -c 'import pytest_cov' >/dev/null 2>&1; then
    printf '%s∼ skipped (pytest-cov not installed — see requirements-dev.txt)%s\n' "$yellow" "$reset"
    return 0
  fi
  python3 -m pytest plugins/dev-team/tests tests/repo tests/agents tests/commands \
    tests/docs tests/knowledge tests/bats tests/skills tests/scripts tests/hooks \
    --ignore=tests/scripts/test_csharp_stryker_net_wrapper.py \
    --ignore=tests/scripts/test_csharp_stryker_net_status_loop.py \
    --cov=plugins/dev-team/hooks --cov=scripts --cov-report=term -q \
    || printf '%s∼ coverage-instrumented run reported test failures — informational only, not gating%s\n' "$yellow" "$reset"
  return 0
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
  "security-assessment MCP tool grant drift (check_security_assessment_mcp_tools.py)::chk_sa_mcp_tools"
  "skills catalog freshness (docs/skills.md)::chk_skills_index"
  "nav integrity (mkdocs nav → assembled file)::chk_nav_integrity"
  "eval-corpus semver contract::chk_eval_semver"
  "eslint::chk_eslint"
  "ruff check (Python lint)::chk_ruff"
  "shipped Python 3.8 floor (compile + import on a real 3.8)::chk_python_floor"
  "plugin hook + script unit tests (pytest plugins/dev-team/tests)::chk_hook_units"
)

# Opt-in-only checks: never run as part of the default (no --only) full gate,
# only reachable via an explicit --only=<fn>. Distinct from the checks above,
# which always run. chk_coverage_report is the first entry — it duplicates
# chk_hook_units's full suite run under coverage instrumentation, so folding
# it into the default gate would roughly double every push's/CI's wall-clock
# for an informational report most invocations don't need. Run it on demand:
# `bash scripts/ci-local.sh --only=chk_coverage_report`.
OPTIONAL_CHECKS=(
  "coverage report (informational; pytest --cov)::chk_coverage_report"
)

# --only=fn[,fn...] : keep just the named checks (CI invokes per-job subsets;
# developers reach OPTIONAL_CHECKS entries the same way).
if [ -n "$ONLY" ]; then
  filtered=()
  for entry in ${CHECKS[@]+"${CHECKS[@]}"} ${OPTIONAL_CHECKS[@]+"${OPTIONAL_CHECKS[@]}"}; do
    fn="${entry##*::}"
    case ",$ONLY," in *",$fn,"*) filtered+=("$entry") ;; esac
  done
  if [ "${#filtered[@]}" -eq 0 ]; then
    printf '%s%sNo checks matched --only=%s%s\n' "$bold" "$red" "$ONLY" "$reset" >&2
    exit 2
  fi
  CHECKS=(${filtered[@]+"${filtered[@]}"})
fi

# _render_timing_if_enabled — opt-in (CI_LOCAL_TIMING=1 exactly). Renders the
# timing section from the per-index files in $RUNDIR, labels in declared CHECKS
# order (index-aligned with the aggregation loop below). Any other flag value —
# 0, false, empty, unset — returns immediately and prints nothing.
_render_timing_if_enabled() {
  [ "${CI_LOCAL_TIMING:-}" = "1" ] || return 0
  local labels=() e
  for e in ${CHECKS[@]+"${CHECKS[@]}"}; do labels+=("${e%%::*}"); done
  ci_render_timing "$RUNDIR" ${labels[@]+"${labels[@]}"}
}

# --- dispatch (bounded FIFO pool; no `wait -n`, so portable to bash 3.2) ----
RUNDIR="$(mktemp -d)"
trap 'rm -rf "$RUNDIR"' EXIT

printf '%srunning %d checks, up to %d in parallel…%s\n' "$bold" "${#CHECKS[@]}" "$JOBS" "$reset"

# Time the entire concurrent dispatch region for the opt-in timing summary. The
# `time` keyword (TIMEFORMAT='%R' -> bare real seconds) is a shell builtin — no
# subprocess, portable to macOS bash 3.2 — and its report is redirected to a file
# in $RUNDIR, so a run with timing disabled pays only the keyword and prints
# nothing extra. `wait` stays inside the timed block so the total is true
# wall-clock, not the sum of per-check times.
TIMEFORMAT='%R'
{ time {
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
  # Time each check with the `time` keyword (TIMEFORMAT='%R' -> bare real
  # seconds) inside its own subshell, writing the real time to a per-index file
  # alongside .out/.rc. One subshell owns each index, so concurrent checks cannot
  # corrupt each other's timing — the same isolation .out/.rc already rely on.
  # $? after the timed group is the check's own exit status (time is transparent).
  ( TIMEFORMAT='%R'
    { time "$fn" >"$RUNDIR/$idx.out" 2>&1; } 2>"$RUNDIR/$idx.time"
    echo $? >"$RUNDIR/$idx.rc" ) &
  pids+=("$!")
  idx=$((idx + 1))
  # Throttle: once JOBS are in flight, block on the oldest before launching more.
  if [ "${#pids[@]}" -ge "$JOBS" ]; then
    wait "${pids[0]}" 2>/dev/null || true
    pids=("${pids[@]:1}")
  fi
done
wait  # drain the remainder
}; } 2>"$RUNDIR/.total.time"

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
  _render_timing_if_enabled
  exit 0
fi
printf '%s%s%d check(s) failed:%s\n' "$bold" "$red" "${#FAILURES[@]}" "$reset" >&2
for f in "${FAILURES[@]}"; do printf '  %s✗ %s%s\n' "$red" "$f" "$reset" >&2; done
_render_timing_if_enabled
exit 1
