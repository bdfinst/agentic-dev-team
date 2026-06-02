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

# AC-14: every package key in release-please-config.json must correspond to
# an extant plugin directory, and every plugins/* directory that ships a
# plugin.json must be a known release-please package. This invariant must
# hold at every commit on the branch.
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
  # Directories that look like plugins (carry a plugin.json). Portable across
  # GNU and BSD find: use -path, no -printf.
  local actual
  actual=$(find plugins -mindepth 3 -maxdepth 3 -type f -path 'plugins/*/.claude-plugin/plugin.json' 2>/dev/null \
    | sed -e 's|/\.claude-plugin/plugin\.json$||' \
    | sort)
  # Normalize: release-please paths are repo-relative without trailing slash.
  if [ "$declared" = "$actual" ]; then
    pass "release-please packages match plugins/ layout"
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
check_manifest_names() {
  if [ -d plugins/agentic-dev-team ]; then
    fail "plugins/agentic-dev-team still exists (expected: plugins/dev-team)"
  else
    pass "plugins/agentic-dev-team is gone"
  fi

  if [ -d plugins/agentic-security-assessment ]; then
    fail "plugins/agentic-security-assessment still exists (expected: plugins/security-assessment)"
  else
    pass "plugins/agentic-security-assessment is gone"
  fi

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
  local expected="dev-team security-assessment "
  if [ "$names" = "$expected" ]; then
    pass "marketplace.json lists exactly: dev-team, security-assessment"
  else
    fail "marketplace.json plugin names = '$names' (expected '$expected')"
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
  [ "$dt" = "dev-team" ] && pass "release-please component = dev-team" || fail "dev-team component = '$dt'"
  [ "$sa" = "security-assessment" ] && pass "release-please component = security-assessment" || fail "security-assessment component = '$sa'"
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
  hits=$(grep -rln "agentic-dev-team" plugins/dev-team/ \
    --exclude=CHANGELOG.md --exclude=upgrade.md 2>/dev/null || true)
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
  local hits
  hits=$(grep -rln 'agentic-security-assessment\|agentic-dev-team' \
    plugins/security-assessment/ \
    --exclude=CHANGELOG.md --exclude=install.sh 2>/dev/null || true)
  if [ -z "$hits" ]; then
    pass "plugins/security-assessment/ free of legacy plugin names"
  else
    fail "plugins/security-assessment/ still references legacy names:"
    printf '%s\n' "$hits" | sed 's/^/        /'
  fi
}

check_security_assessment_body_clean

# --- Summary -------------------------------------------------------------

printf '\n%d passed, %d failed\n' "$pass_count" "$fail_count"
[ "$fail_count" -eq 0 ] || exit 1
