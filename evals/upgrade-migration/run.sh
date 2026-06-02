#!/usr/bin/env bash
# evals/upgrade-migration/run.sh — exercise the /upgrade Step 0 migration
# logic against four fixtures, in dry-run mode (no real plugin operations).
#
# Each fixture sets UPGRADE_INSTALLED_JSON to its installed_plugins.json
# stand-in and runs migrate.py. The test then asserts on stdout content.
#
# Fixtures:
#   a — legacy dev-team only      → migrate to dev-team, exit 0
#   b — legacy security only      → migrate to security-assessment, exit 0
#   c — already-migrated state    → "No legacy plugin ids found", exit 0
#   d — both legacy plugins       → migrate both, summary lists 2, exit 0
#
# Exit codes:
#   0  — all fixtures behaved as expected
#   1  — at least one assertion failed

set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
MIGRATE="$ROOT/evals/upgrade-migration/migrate.py"
FIXTURES="$ROOT/evals/upgrade-migration/fixtures"

fail=0
pass=0

run_fixture() {
  local name="$1" fixture="$2"
  shift 2
  printf '\n── %s ──\n' "$name"
  local output rc
  output=$(UPGRADE_DRY_RUN=1 UPGRADE_INSTALLED_JSON="$fixture" python3 "$MIGRATE" 2>&1)
  rc=$?
  printf '%s\n' "$output"
  printf 'exit=%s\n' "$rc"

  # All remaining args are 'expect <regex>' or '!expect <regex>' or 'exit N'.
  local expectation
  for expectation in "$@"; do
    case "$expectation" in
      "exit "*)
        local expected=${expectation#exit }
        if [ "$rc" = "$expected" ]; then
          pass=$((pass + 1))
          printf '  ok    exit code = %s\n' "$expected"
        else
          fail=$((fail + 1))
          printf '  FAIL  exit code = %s (expected %s)\n' "$rc" "$expected"
        fi
        ;;
      "!expect "*)
        local pattern=${expectation#!expect }
        if printf '%s' "$output" | grep -qE -- "$pattern"; then
          fail=$((fail + 1))
          printf '  FAIL  unexpected match: %s\n' "$pattern"
        else
          pass=$((pass + 1))
          printf '  ok    no match for: %s\n' "$pattern"
        fi
        ;;
      "expect "*)
        local pattern=${expectation#expect }
        if printf '%s' "$output" | grep -qE -- "$pattern"; then
          pass=$((pass + 1))
          printf '  ok    matched: %s\n' "$pattern"
        else
          fail=$((fail + 1))
          printf '  FAIL  no match for: %s\n' "$pattern"
        fi
        ;;
    esac
  done
}

# Fixture A: legacy dev-team only.
run_fixture "A: legacy dev-team only" "$FIXTURES/a-legacy-dev-team.json" \
  "expect Plugin renamed: agentic-dev-team → dev-team" \
  "expect WOULD RUN: claude plugin install --scope user dev-team@bfinster" \
  "expect WOULD RUN: claude plugin uninstall --scope user agentic-dev-team@bfinster" \
  "expect ACTION REQUIRED: restart Claude Code" \
  "exit 0"

# Fixture B: legacy security-assessment only.
run_fixture "B: legacy security-assessment only" "$FIXTURES/b-legacy-security-assessment.json" \
  "expect Plugin renamed: agentic-security-assessment → security-assessment" \
  "expect WOULD RUN: claude plugin install --scope user security-assessment@bfinster" \
  "expect WOULD RUN: claude plugin uninstall --scope user agentic-security-assessment@bfinster" \
  "exit 0"

# Fixture C: already migrated — no work scheduled.
run_fixture "C: already migrated" "$FIXTURES/c-already-migrated.json" \
  "expect No legacy plugin ids found" \
  "!expect WOULD RUN" \
  "!expect Plugin renamed" \
  "exit 0"

# Fixture D: both legacy plugins present.
run_fixture "D: both legacy plugins" "$FIXTURES/d-both-legacy.json" \
  "expect Plugin renamed: agentic-dev-team → dev-team" \
  "expect Plugin renamed: agentic-security-assessment → security-assessment" \
  "expect agentic-dev-team → dev-team$" \
  "expect agentic-security-assessment → security-assessment$" \
  "exit 0"

# Verify install-first-then-uninstall ORDERING for fixture A.
printf '\n── ordering check (install before uninstall, fixture A) ──\n'
ordered=$(UPGRADE_DRY_RUN=1 UPGRADE_INSTALLED_JSON="$FIXTURES/a-legacy-dev-team.json" \
  python3 "$MIGRATE" 2>&1 \
  | grep -nE 'WOULD RUN: claude plugin (install|uninstall)')
printf '%s\n' "$ordered"
install_line=$(printf '%s' "$ordered" | grep "install" | head -1 | cut -d: -f1)
uninstall_line=$(printf '%s' "$ordered" | grep "uninstall" | head -1 | cut -d: -f1)
if [ -n "$install_line" ] && [ -n "$uninstall_line" ] && [ "$install_line" -lt "$uninstall_line" ]; then
  pass=$((pass + 1))
  printf '  ok    install (line %s) scheduled before uninstall (line %s)\n' "$install_line" "$uninstall_line"
else
  fail=$((fail + 1))
  printf '  FAIL  ordering wrong: install=%s uninstall=%s\n' "$install_line" "$uninstall_line"
fi

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ] || exit 1
