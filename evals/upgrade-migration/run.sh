#!/usr/bin/env bash
# evals/upgrade-migration/run.sh — exercise the /upgrade Step 0 migration
# logic against seven fixtures, in dry-run mode (no real plugin operations).
#
# Each fixture sets UPGRADE_INSTALLED_JSON to its installed_plugins.json
# stand-in and runs migrate.py. The test then asserts on stdout content.
# Failure-injection env vars (UPGRADE_DRY_RUN_INSTALL_FAIL,
# UPGRADE_DRY_RUN_UNINSTALL_FAIL) let us exercise the recovery paths
# without needing a real claude binary.
#
# Fixtures:
#   A — legacy dev-team only        → migrate to dev-team, exit 0
#   B — legacy security only        → migrate to security-assessment, exit 0
#   C — already-migrated state      → "No legacy plugin ids found", exit 0
#   D — both legacy plugins         → migrate both, summary lists 2, exit 0
#   E — install-failure injected    → MIGRATION FAILED, exit 1
#   F — uninstall-failure injected  → WARNING, partial success, exit 0
#   G — malformed installed_plugins → diagnostic + skip, exit 0
#   H — missing installed_plugins   → silent skip, exit 0
#
# Plus ordering checks for fixture A (one plugin) and fixture D (two
# plugins, four scheduled commands in strict sequence).
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

# run_fixture <name> <fixture_path> [VAR=val ...] [-- <expectations...>]
# Env vars before the `--` separator are exported into the migrate.py
# invocation. After `--`, all args are 'expect <regex>' / '!expect <regex>'
# / 'exit N'.
run_fixture() {
  local name="$1" fixture="$2"
  shift 2

  local -a env_kv=()
  while [ "$#" -gt 0 ] && [ "$1" != "--" ]; do
    env_kv+=("$1")
    shift
  done
  [ "${1:-}" = "--" ] && shift

  printf '\n── %s ──\n' "$name"
  local output rc
  output=$(env UPGRADE_DRY_RUN=1 UPGRADE_INSTALLED_JSON="$fixture" "${env_kv[@]}" \
    python3 "$MIGRATE" 2>&1)
  rc=$?
  printf '%s\n' "$output"
  printf 'exit=%s\n' "$rc"

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
run_fixture "A: legacy dev-team only" "$FIXTURES/a-legacy-dev-team.json" -- \
  "expect Plugin renamed: agentic-dev-team → dev-team" \
  "expect WOULD RUN: claude plugin install --scope user dev-team@bfinster" \
  "expect WOULD RUN: claude plugin uninstall --scope user agentic-dev-team@bfinster" \
  "expect ACTION REQUIRED: restart Claude Code" \
  "exit 0"

# Fixture B: legacy security-assessment only. Negative guard: no dev-team
# migration should be triggered.
run_fixture "B: legacy security-assessment only" "$FIXTURES/b-legacy-security-assessment.json" -- \
  "expect Plugin renamed: agentic-security-assessment → security-assessment" \
  "expect WOULD RUN: claude plugin install --scope user security-assessment@bfinster" \
  "expect WOULD RUN: claude plugin uninstall --scope user agentic-security-assessment@bfinster" \
  "!expect Plugin renamed: agentic-dev-team" \
  "!expect WOULD RUN: claude plugin install --scope user dev-team@bfinster" \
  "exit 0"

# Fixture C: already migrated — no work scheduled.
run_fixture "C: already migrated" "$FIXTURES/c-already-migrated.json" -- \
  "expect No legacy plugin ids found" \
  "!expect WOULD RUN" \
  "!expect Plugin renamed" \
  "exit 0"

# Fixture D: both legacy plugins present.
run_fixture "D: both legacy plugins" "$FIXTURES/d-both-legacy.json" -- \
  "expect Plugin renamed: agentic-dev-team → dev-team" \
  "expect Plugin renamed: agentic-security-assessment → security-assessment" \
  "expect agentic-dev-team → dev-team$" \
  "expect agentic-security-assessment → security-assessment$" \
  "expect ACTION REQUIRED: restart Claude Code" \
  "exit 0"

# Fixture E: install failure injected. The migration MUST abort with exit 1
# and MUST NOT schedule the uninstall (install-first-then-uninstall safety
# contract). Retry command must be surfaced.
run_fixture "E: install-failure injected" "$FIXTURES/e-install-failure.json" \
  "UPGRADE_DRY_RUN_INSTALL_FAIL=1" -- \
  "expect Plugin renamed: agentic-dev-team → dev-team" \
  "expect WOULD RUN: claude plugin install --scope user dev-team@bfinster  \[injected: rc=1\]" \
  "!expect WOULD RUN: claude plugin uninstall" \
  "expect MIGRATION FAILED" \
  "expect Retry with: claude plugin install --scope user dev-team@bfinster" \
  "!expect ACTION REQUIRED" \
  "exit 1"

# Fixture F: install succeeds, uninstall fails. The migration should
# WARN (partial success) but still exit 0 — the new plugin is live, the
# old plugin is leftover and the user is told how to remove it.
run_fixture "F: uninstall-failure injected" "$FIXTURES/f-uninstall-failure.json" \
  "UPGRADE_DRY_RUN_UNINSTALL_FAIL=1" -- \
  "expect WOULD RUN: claude plugin install --scope user dev-team@bfinster" \
  "expect WOULD RUN: claude plugin uninstall --scope user agentic-dev-team@bfinster  \[injected: rc=1\]" \
  "expect WARNING: install of dev-team@bfinster succeeded but uninstall of agentic-dev-team@bfinster failed" \
  "expect You may have both plugins installed" \
  "expect ACTION REQUIRED: restart Claude Code" \
  "exit 0"

# Fixture G: malformed installed_plugins.json. find_legacy_installs prints
# a diagnostic and returns []; migrate falls through to the no-legacy
# branch and exits 0.
run_fixture "G: malformed installed_plugins.json" "$FIXTURES/g-malformed.json" -- \
  "expect is not valid JSON" \
  "expect No legacy plugin ids found" \
  "!expect WOULD RUN" \
  "exit 0"

# Fixture H: missing installed_plugins.json. FileNotFoundError path:
# silent return, no diagnostic, exit 0.
run_fixture "H: missing installed_plugins.json" "$FIXTURES/__nonexistent__.json" -- \
  "expect No legacy plugin ids found" \
  "!expect WOULD RUN" \
  "!expect is not valid JSON" \
  "exit 0"

# Verify install-first-then-uninstall ORDERING for fixture A (one plugin).
printf '\n── ordering check: fixture A (one plugin) ──\n'
ordered=$(UPGRADE_DRY_RUN=1 UPGRADE_INSTALLED_JSON="$FIXTURES/a-legacy-dev-team.json" \
  python3 "$MIGRATE" 2>&1) || true
filtered=$(printf '%s' "$ordered" | grep -nE 'WOULD RUN: claude plugin (install|uninstall)' || true)
printf '%s\n' "$filtered"
if [ -z "$filtered" ]; then
  fail=$((fail + 1))
  printf '  FAIL  ordering check: no scheduled commands captured\n'
else
  install_line=$(printf '%s' "$filtered" | grep "install --scope" | head -1 | cut -d: -f1)
  uninstall_line=$(printf '%s' "$filtered" | grep "uninstall --scope" | head -1 | cut -d: -f1)
  if [ -n "$install_line" ] && [ -n "$uninstall_line" ] && [ "$install_line" -lt "$uninstall_line" ]; then
    pass=$((pass + 1))
    printf '  ok    install (line %s) before uninstall (line %s)\n' "$install_line" "$uninstall_line"
  else
    fail=$((fail + 1))
    printf '  FAIL  ordering wrong: install=%s uninstall=%s\n' "$install_line" "$uninstall_line"
  fi
fi

# Verify ordering for fixture D (two plugins, four scheduled commands):
# install dev-team → uninstall agentic-dev-team → install security-assessment → uninstall agentic-security-assessment.
printf '\n── ordering check: fixture D (two plugins) ──\n'
ordered_d=$(UPGRADE_DRY_RUN=1 UPGRADE_INSTALLED_JSON="$FIXTURES/d-both-legacy.json" \
  python3 "$MIGRATE" 2>&1) || true
filtered_d=$(printf '%s' "$ordered_d" | grep -nE 'WOULD RUN: claude plugin (install|uninstall)' || true)
printf '%s\n' "$filtered_d"
expected_order='install --scope user dev-team@bfinster
uninstall --scope user agentic-dev-team@bfinster
install --scope user security-assessment@bfinster
uninstall --scope user agentic-security-assessment@bfinster'
actual_order=$(printf '%s' "$filtered_d" | sed -E 's/^[0-9]+:[[:space:]]*WOULD RUN: claude plugin //; s/  \[injected:.*\]//')
if [ "$actual_order" = "$expected_order" ]; then
  pass=$((pass + 1))
  printf '  ok    fixture D scheduled commands in expected install-then-uninstall sequence for both plugins\n'
else
  fail=$((fail + 1))
  printf '  FAIL  fixture D ordering does not match expected sequence\n'
  printf '        expected:\n%s\n' "$expected_order" | sed 's/^/          /'
  printf '        actual:\n%s\n' "$actual_order" | sed 's/^/          /'
fi

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ] || exit 1
