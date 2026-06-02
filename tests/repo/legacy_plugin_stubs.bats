#!/usr/bin/env bats
#
# tests/repo/legacy_plugin_stubs.bats — invariants for the deprecation
# stubs published under the old plugin ids (agentic-dev-team,
# agentic-security-assessment).
#
# Spec: docs/specs/legacy-plugin-stubs.md
# Acceptance criteria LSAC-1 through LSAC-7.

setup() {
  REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
  STUB_DEV="$REPO_ROOT/plugins/agentic-dev-team"
  STUB_SEC="$REPO_ROOT/plugins/agentic-security-assessment"
}

# LSAC-1: required files present in each stub
@test "LSAC-1: agentic-dev-team stub has plugin.json, upgrade.md, README, CHANGELOG" {
  [ -f "$STUB_DEV/.claude-plugin/plugin.json" ]
  [ -f "$STUB_DEV/commands/upgrade.md" ]
  [ -f "$STUB_DEV/README.md" ]
  [ -f "$STUB_DEV/CHANGELOG.md" ]
}

@test "LSAC-1: agentic-security-assessment stub has plugin.json, upgrade.md, README, CHANGELOG" {
  [ -f "$STUB_SEC/.claude-plugin/plugin.json" ]
  [ -f "$STUB_SEC/commands/upgrade.md" ]
  [ -f "$STUB_SEC/README.md" ]
  [ -f "$STUB_SEC/CHANGELOG.md" ]
}

# LSAC-2: plugin.json declares old name + version newer than last real release
@test "LSAC-2: agentic-dev-team stub plugin.json declares legacy name and bumped version" {
  local name version
  name=$(jq -r .name "$STUB_DEV/.claude-plugin/plugin.json")
  version=$(jq -r .version "$STUB_DEV/.claude-plugin/plugin.json")
  [ "$name" = "agentic-dev-team" ]
  # Stub version must be newer than the last pre-rename release (5.6.0)
  # so `claude plugin update` sees the catalog version as newer than
  # what the user has installed.
  case "$version" in
    6.*|7.*|8.*|9.*) ;;
    *) printf 'stub version %s is not >= 6.x\n' "$version" >&2; return 1 ;;
  esac
}

@test "LSAC-2: agentic-security-assessment stub plugin.json declares legacy name and bumped version" {
  local name version
  name=$(jq -r .name "$STUB_SEC/.claude-plugin/plugin.json")
  version=$(jq -r .version "$STUB_SEC/.claude-plugin/plugin.json")
  [ "$name" = "agentic-security-assessment" ]
  # Stub version must be newer than the last pre-rename release (2.2.2).
  case "$version" in
    3.*|4.*|5.*|6.*|7.*|8.*|9.*) ;;
    *) printf 'stub version %s is not >= 3.x\n' "$version" >&2; return 1 ;;
  esac
}

# LSAC-3: descriptions marked DEPRECATED in BOTH plugin.json and marketplace.json
@test "LSAC-3: agentic-dev-team stub plugin.json marks itself DEPRECATED" {
  local desc
  desc=$(jq -r .description "$STUB_DEV/.claude-plugin/plugin.json")
  echo "$desc" | grep -qi 'DEPRECATED'
}

@test "LSAC-3: agentic-security-assessment stub plugin.json marks itself DEPRECATED" {
  local desc
  desc=$(jq -r .description "$STUB_SEC/.claude-plugin/plugin.json")
  echo "$desc" | grep -qi 'DEPRECATED'
}

@test "LSAC-3: marketplace.json stub entries marked DEPRECATED" {
  local mp="$REPO_ROOT/.claude-plugin/marketplace.json"
  jq -e '.plugins[] | select(.name == "agentic-dev-team") | .description' "$mp" | grep -qi 'DEPRECATED'
  jq -e '.plugins[] | select(.name == "agentic-security-assessment") | .description' "$mp" | grep -qi 'DEPRECATED'
}

# LSAC-4: stub directories contain NO non-stub subdirectories
@test "LSAC-4: agentic-dev-team stub has no agents/skills/knowledge/templates/prompts/harness/hooks" {
  for forbidden in agents skills knowledge templates prompts harness hooks; do
    if [ -d "$STUB_DEV/$forbidden" ]; then
      printf 'forbidden subdirectory present: %s/%s\n' "$STUB_DEV" "$forbidden" >&2
      return 1
    fi
  done
}

@test "LSAC-4: agentic-security-assessment stub has no agents/skills/knowledge/templates/prompts/harness/hooks" {
  for forbidden in agents skills knowledge templates prompts harness hooks; do
    if [ -d "$STUB_SEC/$forbidden" ]; then
      printf 'forbidden subdirectory present: %s/%s\n' "$STUB_SEC" "$forbidden" >&2
      return 1
    fi
  done
}

# LSAC-5: marketplace.json lists all four ids
@test "LSAC-5: marketplace.json plugins[] contains both stubs and both real plugins" {
  local mp="$REPO_ROOT/.claude-plugin/marketplace.json"
  local names
  names=$(jq -r '.plugins[].name' "$mp" | sort | tr '\n' ' ')
  [ "$names" = "agentic-dev-team agentic-security-assessment dev-team security-assessment " ]
}

# LSAC-6: release-please does NOT track the stubs
@test "LSAC-6: release-please-config.json excludes the stub directories" {
  local cfg="$REPO_ROOT/release-please-config.json"
  jq -e '.packages | (has("plugins/agentic-dev-team") | not) and (has("plugins/agentic-security-assessment") | not)' "$cfg" >/dev/null
}

@test "LSAC-6: .release-please-manifest.json excludes the stub directories" {
  local m="$REPO_ROOT/.release-please-manifest.json"
  jq -e '(has("plugins/agentic-dev-team") | not) and (has("plugins/agentic-security-assessment") | not)' "$m" >/dev/null
}

# LSAC-7: each stub's /upgrade body documents the migration contract
@test "LSAC-7: agentic-dev-team /upgrade documents install-first-then-uninstall + scope + restart" {
  local up="$STUB_DEV/commands/upgrade.md"
  # Install must appear BEFORE uninstall in the document body.
  local install_line uninstall_line
  install_line=$(grep -n 'claude plugin install --scope' "$up" | head -1 | cut -d: -f1)
  uninstall_line=$(grep -n 'claude plugin uninstall --scope' "$up" | head -1 | cut -d: -f1)
  [ -n "$install_line" ] && [ -n "$uninstall_line" ] && [ "$install_line" -lt "$uninstall_line" ]
  # Hard gate language on install failure.
  grep -qi 'STOP' "$up"
  grep -qi 'Retry with' "$up"
  # Scope detection.
  grep -qi 'claude plugin list' "$up"
  # Restart prompt.
  grep -qi 'restart Claude Code' "$up"
  # Names the destination plugin.
  grep -q 'dev-team@bfinster' "$up"
}

@test "LSAC-7: agentic-security-assessment /upgrade documents install-first-then-uninstall + scope + restart" {
  local up="$STUB_SEC/commands/upgrade.md"
  local install_line uninstall_line
  install_line=$(grep -n 'claude plugin install --scope' "$up" | head -1 | cut -d: -f1)
  uninstall_line=$(grep -n 'claude plugin uninstall --scope' "$up" | head -1 | cut -d: -f1)
  [ -n "$install_line" ] && [ -n "$uninstall_line" ] && [ "$install_line" -lt "$uninstall_line" ]
  grep -qi 'STOP' "$up"
  grep -qi 'Retry with' "$up"
  grep -qi 'claude plugin list' "$up"
  grep -qi 'restart Claude Code' "$up"
  grep -q 'security-assessment@bfinster' "$up"
}
