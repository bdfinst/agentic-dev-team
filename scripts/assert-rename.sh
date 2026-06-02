#!/usr/bin/env bash
# scripts/assert-rename.sh — invariants for the plugin-rename refactor.
#
# Runs a battery of checks against the repo root and exits non-zero on the
# first failure. Each step in plans/rename-plugins.md extends this script
# with the assertions it expects to satisfy.
#
# Modes:
#   (default)            — run every assertion
#   --consistency-only   — run only the cross-commit consistency checks
#                          (used by Step 8 to replay against each commit on
#                          the branch). Must remain a strict subset of the
#                          full run.
#
# Exit codes:
#   0  — all selected assertions passed
#   1  — at least one assertion failed

set -u

MODE="all"
case "${1:-}" in
  --consistency-only) MODE="consistency" ;;
  "") ;;
  *)
    echo "usage: $0 [--consistency-only]" >&2
    exit 2
    ;;
esac

fail_count=0
pass_count=0

# Resolve repo root so the script works regardless of CWD.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 2

fail() {
  printf '  FAIL  %s\n' "$1"
  fail_count=$((fail_count + 1))
}

pass() {
  printf '  ok    %s\n' "$1"
  pass_count=$((pass_count + 1))
}

# --- Consistency checks (always run) -------------------------------------

# Deprecation stubs are deliberately NOT in release-please-config.json —
# they're manually versioned and short-lived. The consistency check
# excludes them.
LEGACY_STUB_DIRS="plugins/agentic-dev-team plugins/agentic-security-assessment"

# AC-14: every package key in release-please-config.json must correspond to
# an extant plugin directory, and every plugins/* directory that ships a
# plugin.json (excluding deprecation stubs) must be a known release-please
# package. This invariant must hold at every commit on the branch.
check_release_please_consistency() {
  if [ ! -f release-please-config.json ]; then
    fail "release-please-config.json missing"
    return
  fi
  # Packages declared in release-please.
  local declared
  declared=$(jq -r '.packages | keys[]' release-please-config.json 2>/dev/null | sort)
  if [ -z "$declared" ]; then
    fail "release-please-config.json has no packages"
    return
  fi
  # Directories that look like plugins (carry a plugin.json), minus
  # explicitly excluded deprecation stubs. Portable across GNU and BSD find.
  local actual
  actual=$(find plugins -mindepth 3 -maxdepth 3 -type f -path 'plugins/*/.claude-plugin/plugin.json' 2>/dev/null \
    | sed -e 's|/\.claude-plugin/plugin\.json$||' \
    | grep -vE "^($(printf '%s' "$LEGACY_STUB_DIRS" | tr ' ' '|'))$" \
    | sort)
  if [ "$declared" = "$actual" ]; then
    pass "release-please packages match plugins/ layout (excluding deprecation stubs)"
  else
    fail "release-please packages diverge from plugins/ layout"
    printf '        declared: %s\n' "$declared" | tr '\n' ' '; echo
    printf '        on-disk : %s\n' "$actual" | tr '\n' ' '; echo
  fi
}

check_release_please_consistency

if [ "$MODE" = "consistency" ]; then
  printf '\n%d passed, %d failed (consistency subset)\n' "$pass_count" "$fail_count"
  [ "$fail_count" -eq 0 ] || exit 1
  exit 0
fi

# --- Full assertion suite (added to as later steps land) -----------------

# Step 2 invariants (manifest names, depends-on, marketplace catalog, dirs).
# After the deprecation-stub work landed, plugins/agentic-* directories are
# allowed to exist as long as they are stub-shaped (no agents/, no skills/,
# only an /upgrade command).
check_manifest_names() {
  if [ ! -d plugins/dev-team ]; then
    fail "plugins/dev-team missing"
  else
    pass "plugins/dev-team exists"
  fi

  if [ ! -d plugins/security-assessment ]; then
    fail "plugins/security-assessment missing"
  else
    pass "plugins/security-assessment exists"
  fi

  # Deprecation stubs must remain narrow: only /upgrade, no agents, no skills,
  # no hooks beyond a settings.json stub if any. This prevents the stub from
  # silently regrowing into a duplicate of the real plugin.
  check_stub_is_minimal() {
    local stub_dir="$1"
    if [ ! -d "$stub_dir" ]; then
      return  # stub directory absent is fine — already migrated/removed
    fi
    local forbidden
    # hooks/ is allowed but must contain ONLY the deprecation banner.
    forbidden=$(find "$stub_dir" -mindepth 1 -maxdepth 2 -type d \
      \( -name agents -o -name skills -o -name knowledge -o -name templates -o -name prompts -o -name harness \) 2>/dev/null)
    if [ -n "$forbidden" ]; then
      fail "$stub_dir has non-stub subdirectories: $(printf '%s ' "$forbidden")"
    else
      pass "$stub_dir is stub-shaped (no agents/skills/knowledge/etc.)"
    fi
    # The stub MUST ship /upgrade — that's its entire reason to exist.
    if [ -f "$stub_dir/commands/upgrade.md" ]; then
      pass "$stub_dir/commands/upgrade.md present"
    else
      fail "$stub_dir/commands/upgrade.md missing — stub has no migration command"
    fi
  }
  check_stub_is_minimal plugins/agentic-dev-team
  check_stub_is_minimal plugins/agentic-security-assessment

  if [ -f plugins/dev-team/.claude-plugin/plugin.json ]; then
    local name
    name=$(jq -r .name plugins/dev-team/.claude-plugin/plugin.json)
    if [ "$name" = "dev-team" ]; then
      pass "dev-team plugin.json name = dev-team"
    else
      fail "dev-team plugin.json name = '$name' (expected 'dev-team')"
    fi
  else
    fail "plugins/dev-team/.claude-plugin/plugin.json missing"
  fi

  if [ -f plugins/security-assessment/.claude-plugin/plugin.json ]; then
    local name dep
    name=$(jq -r .name plugins/security-assessment/.claude-plugin/plugin.json)
    dep=$(jq -r '.["depends-on"][0].name // empty' plugins/security-assessment/.claude-plugin/plugin.json)
    if [ "$name" = "security-assessment" ]; then
      pass "security-assessment plugin.json name = security-assessment"
    else
      fail "security-assessment plugin.json name = '$name' (expected 'security-assessment')"
    fi
    if [ "$dep" = "dev-team" ]; then
      pass "security-assessment depends-on[0].name = dev-team"
    else
      fail "security-assessment depends-on[0].name = '$dep' (expected 'dev-team')"
    fi
  else
    fail "plugins/security-assessment/.claude-plugin/plugin.json missing"
  fi
}

check_manifest_names

check_marketplace_catalog() {
  if [ ! -f .claude-plugin/marketplace.json ]; then
    fail ".claude-plugin/marketplace.json missing"
    return
  fi
  local names
  names=$(jq -r '.plugins[].name' .claude-plugin/marketplace.json | sort | tr '\n' ' ')
  # Real plugins + deprecation stubs are both expected. Order is alphabetical
  # after `sort`: agentic-dev-team, agentic-security-assessment, dev-team,
  # security-assessment.
  local expected="agentic-dev-team agentic-security-assessment dev-team security-assessment "
  if [ "$names" = "$expected" ]; then
    pass "marketplace.json lists real plugins + deprecation stubs"
  else
    fail "marketplace.json plugin names = '$names' (expected '$expected')"
  fi
  # Stubs MUST be marked deprecated in their description so anyone browsing
  # the catalog sees the deprecation immediately.
  local stub_descs
  stub_descs=$(jq -r '.plugins[] | select(.name == "agentic-dev-team" or .name == "agentic-security-assessment") | .description' .claude-plugin/marketplace.json)
  if printf '%s' "$stub_descs" | grep -q -i 'DEPRECATED'; then
    pass "marketplace stub descriptions mark them DEPRECATED"
  else
    fail "marketplace stub descriptions do not contain 'DEPRECATED'"
  fi
}

check_marketplace_catalog

check_release_please_components() {
  if [ ! -f release-please-config.json ]; then
    fail "release-please-config.json missing (already reported)"
    return
  fi
  local ok
  ok=$(jq -e '
    .packages
    | has("plugins/dev-team")
    and has("plugins/security-assessment")
    and (has("plugins/agentic-dev-team") | not)
    and (has("plugins/agentic-security-assessment") | not)
  ' release-please-config.json 2>/dev/null)
  if [ "$ok" = "true" ]; then
    pass "release-please-config.json packages use new paths only"
  else
    fail "release-please-config.json packages still reference old paths"
  fi
  local dt sa
  dt=$(jq -r '.packages["plugins/dev-team"].component // empty' release-please-config.json)
  sa=$(jq -r '.packages["plugins/security-assessment"].component // empty' release-please-config.json)
  if [ "$dt" = "dev-team" ]; then
    pass "release-please component = dev-team"
  else
    fail "dev-team component = '$dt'"
  fi
  if [ "$sa" = "security-assessment" ]; then
    pass "release-please component = security-assessment"
  else
    fail "security-assessment component = '$sa'"
  fi
}

check_release_please_components

check_release_please_manifest() {
  if [ ! -f .release-please-manifest.json ]; then
    fail ".release-please-manifest.json missing"
    return
  fi
  local ok
  ok=$(jq -e '
    has("plugins/dev-team")
    and has("plugins/security-assessment")
    and (has("plugins/agentic-dev-team") | not)
    and (has("plugins/agentic-security-assessment") | not)
  ' .release-please-manifest.json 2>/dev/null)
  if [ "$ok" = "true" ]; then
    pass ".release-please-manifest.json keys use new paths only"
  else
    fail ".release-please-manifest.json keys still reference old paths"
  fi
}

check_release_please_manifest

# Step 3 invariant: no live references to old name in plugins/dev-team/
# except CHANGELOG.md (history) and commands/upgrade.md (migration block).
check_dev_team_body_clean() {
  local hits
  # Skip the deprecation stub directory — legitimate home for the legacy name.
  hits=$(grep -rln "agentic-dev-team" plugins/dev-team/ \
    --exclude=CHANGELOG.md --exclude=upgrade.md 2>/dev/null \
    | grep -v '^plugins/agentic-dev-team/' || true)
  if [ -z "$hits" ]; then
    pass "plugins/dev-team/ free of agentic-dev-team references"
  else
    fail "plugins/dev-team/ still references agentic-dev-team:"
    printf '%s\n' "$hits" | sed 's/^/        /'
  fi
}

check_dev_team_body_clean

# Step 4 invariant: no live references to either old name in
# plugins/security-assessment/ except CHANGELOG.md (history) and install.sh
# (intentional legacy-detection migration notice).
check_security_assessment_body_clean() {
  # The plugin's /upgrade and README intentionally describe the legacy
  # migration path; the deprecation stub does the actual migration.
  local hits
  hits=$(grep -rln 'agentic-security-assessment\|agentic-dev-team' \
    plugins/security-assessment/ \
    --exclude=CHANGELOG.md --exclude=install.sh \
    --exclude=upgrade.md --exclude=README.md 2>/dev/null || true)
  if [ -z "$hits" ]; then
    pass "plugins/security-assessment/ free of legacy plugin names"
  else
    fail "plugins/security-assessment/ still references legacy names:"
    printf '%s\n' "$hits" | sed 's/^/        /'
  fi
}

check_security_assessment_body_clean

# Step 5 invariant: /upgrade has a Step 0 migration block that invokes
# evals/upgrade-migration/migrate.py, and the eval runner is present.
check_upgrade_step0() {
  local upgrade=plugins/dev-team/commands/upgrade.md
  if [ ! -f "$upgrade" ]; then
    fail "$upgrade missing"
    return
  fi
  if grep -q '^### 0\. Detect and migrate legacy plugin ids' "$upgrade"; then
    pass "/upgrade has Step 0 migration heading"
  else
    fail "/upgrade missing Step 0 migration heading"
  fi
  if grep -q 'evals/upgrade-migration/migrate\.py' "$upgrade"; then
    pass "/upgrade Step 0 invokes evals/upgrade-migration/migrate.py"
  else
    fail "/upgrade Step 0 does not reference evals/upgrade-migration/migrate.py"
  fi
  if [ -x evals/upgrade-migration/migrate.py ] && [ -x evals/upgrade-migration/run.sh ]; then
    pass "evals/upgrade-migration/{migrate.py,run.sh} present and executable"
  else
    fail "evals/upgrade-migration/{migrate.py,run.sh} missing or not executable"
  fi
}

check_upgrade_step0

# Step 6 invariant: no live references to old names in tracked files
# outside the explicit exclusion list. We restrict to `git ls-files` so
# gitignored runtime artifacts (memory/recon-*, reports/, __pycache__/) and
# user-private files don't generate noise. Line-level matches let us
# preserve the unavoidable github.com/bdfinst/agentic-dev-team URL (the
# actual repository name, out of scope) and the "Previously published as"
# discoverability sentence in the marketplace catalog.
check_no_live_legacy_references() {
  # Use git ls-files -z to get NUL-separated tracked filenames (handles
  # spaces / newlines in paths) and pipe straight into xargs -0. xargs and
  # grep both exit 1 on "no match" which is success here, so we must
  # distinguish that from exit codes >= 2 (real invocation errors like
  # "argument list too long" or a missing tool).
  local raw_hits rc_pipeline
  set +e +u
  raw_hits=$(git ls-files -z 2>/dev/null \
    | xargs -0 grep -nE 'agentic-dev-team|agentic-security-assessment' 2>/dev/null)
  rc_pipeline=${PIPESTATUS[1]:-0}
  set -u
  # xargs/grep: 0 = matches, 1 = no matches (clean pass), >=2 = invocation error.
  if [ "$rc_pipeline" -ge 2 ]; then
    fail "xargs/grep invocation failed (rc=$rc_pipeline); cannot verify legacy references"
    return
  fi
  local hits
  hits=$(printf '%s\n' "$raw_hits" \
    | grep -vE '(github\.com/bdfinst/agentic-dev-team|Previously published as|DEPRECATED|"name": "agentic-(dev-team|security-assessment)"|"source": "\./plugins/agentic-(dev-team|security-assessment)")' \
    | grep -vE '^(CHANGELOG\.md|.*/CHANGELOG\.md|metrics/config-changelog\.jsonl|memory/decisions\.md|plans/|docs/adr/|docs/specs/rename-plugins\.md|docs/specs/legacy-plugin-stubs\.md|docs/decisions/upgrade-step-0-sunset\.md|evals/security-review-adapter/|evals/upgrade-migration/|plugins/dev-team/commands/upgrade\.md|plugins/security-assessment/install\.sh|plugins/security-assessment/commands/upgrade\.md|plugins/security-assessment/README\.md|plugins/agentic-dev-team/|plugins/agentic-security-assessment/|scripts/assert-rename\.sh|scripts/sweep-rename\.sh|tests/repo/legacy_plugin_stubs\.bats|tests/commands/security_upgrade_tests\.bats|README\.md)' \
    || true)
  if [ -z "$hits" ]; then
    pass "no live references to legacy plugin names in tracked files"
  else
    fail "live references to legacy plugin names found in tracked files:"
    printf '%s\n' "$hits" | head -40 | sed 's/^/        /'
  fi
}

check_no_live_legacy_references

# Step 6 invariant: top-level README has a Renamed plugins notice.
check_readme_renamed_notice() {
  if [ ! -f README.md ]; then
    fail "top-level README.md missing"
    return
  fi
  # The notice may be a blockquote-style heading ('> ## Renamed plugins') or
  # a top-level section, as long as it names both old → new and gives the
  # new install commands.
  if grep -qE '^>?[[:space:]]*##+ .*Renamed' README.md && \
     grep -q 'agentic-dev-team' README.md && \
     grep -q 'agentic-security-assessment' README.md && \
     grep -q 'dev-team@bfinster' README.md && \
     grep -q 'security-assessment@bfinster' README.md; then
    pass "README.md has Renamed-plugins notice with old→new pairs and new install commands"
  else
    fail "README.md is missing the Renamed-plugins notice"
  fi
}

check_readme_renamed_notice

# Step 7 invariant: every script invoked by .github/workflows/plugin-tests.yml
# exits zero. Skipped if shellcheck is missing (CI installs it; local devs
# may not have it).
check_ci_scripts() {
  if ! command -v shellcheck >/dev/null 2>&1; then
    # Skip without incrementing pass/fail — shellcheck is a CI tool; a
    # missing local install is not a passing check, just an unverified one.
    printf '  skip  ci scripts (shellcheck not installed locally; CI verifies)\n'
    return
  fi
  if shellcheck -x \
       plugins/security-assessment/scripts/_lib.sh \
       plugins/security-assessment/scripts/apply-accepted-risks.sh \
       plugins/security-assessment/scripts/apply-severity-floors.sh \
       plugins/security-assessment/scripts/find-ci-files.sh \
       plugins/security-assessment/scripts/phase-timer.sh \
       >/dev/null 2>&1; then
    pass "shellcheck passes on security-assessment helper scripts"
  else
    fail "shellcheck failed on security-assessment helper scripts"
  fi
  if shellcheck plugins/security-assessment/tests/scripts/*.sh >/dev/null 2>&1; then
    pass "shellcheck passes on security-assessment test scripts"
  else
    fail "shellcheck failed on security-assessment test scripts"
  fi
  if bash plugins/security-assessment/tests/scripts/run-all.sh >/dev/null 2>&1; then
    pass "plugins/security-assessment/tests/scripts/run-all.sh exits zero"
  else
    fail "plugins/security-assessment/tests/scripts/run-all.sh failed"
  fi
}

check_ci_scripts

# --- Summary -------------------------------------------------------------

printf '\n%d passed, %d failed\n' "$pass_count" "$fail_count"
[ "$fail_count" -eq 0 ] || exit 1
