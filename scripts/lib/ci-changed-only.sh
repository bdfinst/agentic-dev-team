#!/usr/bin/env bash
# ci-changed-only.sh — suite -> watched-path mapping and change-matching helpers
# for ci-local.sh's --changed-only flag. SOURCED, not executed.
#
# The git interaction (resolving the changed-file set) stays in ci-local.sh; this
# file holds only the pure mapping + matching logic so it is unit-testable
# (tests/scripts/test_ci_changed_only.py) without a contrived git history.
#
# bash 3.2 safe: the mapping is a case statement, not an associative array.

# ci_watched_paths <check-fn-name>
# Echoes the space-separated paths a check watches. Entry shapes:
#   - trailing slash ("tests/repo/")  -> directory prefix
#   - contains '*'   ("*.js")          -> glob (matched against the full path)
#   - anything else  ("scripts/x.sh")  -> exact file path
# An unmapped check echoes nothing; callers treat empty as "always run", so a
# new check is never silently skipped just because no mapping was added for it.
ci_watched_paths() {
  case "$1" in
    chk_shellcheck_helpers) printf '%s' "plugins/security-assessment/scripts/" ;;
    chk_shellcheck_tests)   printf '%s' "tests/security-assessment/scripts/" ;;
    chk_sa_shell_suite)     printf '%s' "plugins/security-assessment/ tests/security-assessment/" ;;
    chk_model_routing)      printf '%s' "tests/hooks/ plugins/dev-team/hooks/" ;;
    chk_cost_regression)    printf '%s' "scripts/cost-regression-check.sh scripts/session_extract.py" ;;
    chk_eval_corpus)        printf '%s' "evals/ scripts/eval_grade.py scripts/eval_graders/" ;;
    chk_citation_lint)      printf '%s' "plugins/dev-team/ evals/ scripts/citation_lint.py" ;;
    chk_eval_semver)        printf '%s' "evals/" ;;
    chk_eslint)             printf '%s' "plugins/dev-team/ *.js *.ts *.json" ;;
    chk_ruff)               printf '%s' "*.py ruff.toml" ;;
    chk_oe_staleness)       printf '%s' "" ;;  # advisory; intentionally always-run (no stable watched path)
    chk_parity)             printf '%s' "plugins/dev-team/tests/hooks/parity/ plugins/dev-team/hooks/" ;;
    chk_sa_mcp_tools)       printf '%s' "plugins/security-assessment/agents/ plugins/dev-team/scripts/check_security_assessment_mcp_tools.py plugins/dev-team/scripts/lib/mcp_tool_grants.py" ;;
    *)                      printf '%s' "" ;;
  esac
}

# ci_suite_has_changes <check-fn-name> <changed-files>
# <changed-files> is a whitespace-separated list of changed paths.
# Returns 0 (run the suite) when the suite is unmapped, or when any watched path
# matches a changed file. Returns 1 (skippable) otherwise.
ci_suite_has_changes() {
  local fn="$1"
  local changed="$2"
  local paths
  paths="$(ci_watched_paths "$fn")"
  [ -z "$paths" ] && return 0

  # Disable pathname expansion while splitting watched paths: a glob entry like
  # '*.js' must be matched against the changed-file list (the case below), never
  # expanded against the working directory. set -f does not affect case-pattern
  # matching, so the glob still matches there. Restore the prior state on exit.
  local had_noglob=0
  case "$-" in *f*) had_noglob=1 ;; *) set -f ;; esac

  local rc=1 p f
  for p in $paths; do
    for f in $changed; do
      # $p is intentionally used as a glob pattern in the inner case below.
      # shellcheck disable=SC2254
      case "$p" in
        */)    case "$f" in "$p"*) rc=0 ;; esac ;;
        *'*'*) case "$f" in $p) rc=0 ;; esac ;;
        *)     [ "$f" = "$p" ] && rc=0 ;;
      esac
      [ "$rc" -eq 0 ] && break 2
    done
  done

  [ "$had_noglob" -eq 1 ] || set +f
  return "$rc"
}

# ---------------------------------------------------------------------------
# Inert-path lever (#2003) — a SECOND, independent skip mechanism.
#
# ci_watched_paths/ci_suite_has_changes above are EXISTENTIAL: run if ANY
# changed file matches a watched path. Skipping under that form requires the
# mapping to be a permanent SUPERSET of everything a suite observes, and a
# forgotten path produces a FALSE SKIP — silent, CI-only. For chk_hook_units
# that superset is already 13+ open-ended top-level paths (.claude/, docs/,
# evals/, .husky/, .github/, README.md, package.json, package-lock.json,
# .claude-plugin/, ruff.toml, plugins/, scripts/, tests/) and grows with every
# new content-guard. That is the hand-maintained-denylist shape CLAUDE.md
# documents for the Python floor.
#
# This lever inverts the quantifier. It is UNIVERSAL: skip only when EVERY
# changed file is provably inert. A path nobody has classified simply is not in
# the set, so the omission costs a wasted run and never correctness.
#
#   Watched-path  : forget a path -> false SKIP  -> silent, CI-only
#   Inert-allowlist: forget a path -> false RUN  -> wasted minutes
#
# ci_inert_paths <check-fn-name>
# Echoes the space-separated paths a check PROVABLY CANNOT OBSERVE. Entry
# shapes match ci_watched_paths. An unmapped check echoes nothing, and an empty
# set can never satisfy the universal test below, so unmapped means never
# skipped by this lever — the same safe default the existential form uses.
#
# Grow a set ONLY with a test proving the added path is unobserved
# (tests/scripts/test_ci_changed_only.py). Deliberately NOT inert for
# chk_hook_units: docs/**, *.md, and docs/adr/** — tests/repo reads all three.
# test_adr_readme_toc_complete.py exists because ADRs 0013/0014/0015 landed
# without README entries (#732); making docs/adr/ inert would let that recur.
ci_inert_paths() {
  case "$1" in
    # Non-shipping repo metadata that no test under the chk_hook_units
    # directory list ever READS from disk; pinned by test_ci_changed_only.py.
    #
    # `.gitignore` is deliberately NOT here, though #2003 proposed it: the
    # suite reads the root .gitignore in at least three places
    # (tests/repo/test_gitignore_overrides.py,
    # test_gitignore_gate_bypass_audit.py, tests/skills/
    # test_setup_gitignore_hygiene.py). The guard test caught that seed being
    # wrong, which is the lever working as designed.
    chk_hook_units) printf '%s' "LICENSE .gitattributes" ;;
    *)              printf '%s' "" ;;
  esac
}

# ci_path_is_inert <path> <inert-paths>
# Returns 0 when <path> matches one of the inert entries. Shared matcher so the
# entry shapes cannot drift from ci_suite_has_changes's.
ci_path_is_inert() {
  local f="$1"
  local paths="$2"
  local had_noglob=0
  case "$-" in *f*) had_noglob=1 ;; *) set -f ;; esac

  local rc=1 p
  for p in $paths; do
    # $p is intentionally used as a glob pattern in the case below.
    # shellcheck disable=SC2254
    case "$p" in
      */)    case "$f" in "$p"*) rc=0 ;; esac ;;
      *'*'*) case "$f" in $p) rc=0 ;; esac ;;
      *)     [ "$f" = "$p" ] && rc=0 ;;
    esac
    [ "$rc" -eq 0 ] && break
  done

  [ "$had_noglob" -eq 1 ] || set +f
  return "$rc"
}

# ci_suite_is_all_inert <check-fn-name> <changed-files>
# Returns 0 (skippable) only when the changed set is NON-EMPTY and EVERY file
# in it is inert for this check. Returns 1 (run) otherwise — including an
# unmapped check, an empty inert set, and an empty changed set, each of which
# preserves today's behavior exactly.
ci_suite_is_all_inert() {
  local fn="$1"
  local changed="$2"
  local paths
  paths="$(ci_inert_paths "$fn")"
  [ -z "$paths" ] && return 1
  [ -z "$changed" ] && return 1

  local f
  for f in $changed; do
    ci_path_is_inert "$f" "$paths" || return 1
  done
  return 0
}
