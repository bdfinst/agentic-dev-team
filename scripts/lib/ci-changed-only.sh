#!/usr/bin/env bash
# ci-changed-only.sh — suite -> watched-path mapping and change-matching helpers
# for ci-local.sh's --changed-only flag. SOURCED, not executed.
#
# The git interaction (resolving the changed-file set) stays in ci-local.sh; this
# file holds only the pure mapping + matching logic so it is unit-testable
# (tests/scripts/ci_changed_only_tests.bats) without a contrived git history.
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
