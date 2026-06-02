#!/usr/bin/env bats
#
# tests/commands/security_upgrade_tests.bats — structural invariants for
# the security-assessment plugin's /upgrade command. The plugin ships its
# own /upgrade (parallel to dev-team's) so users with only the security
# plugin installed have an in-session update path.

setup() {
  REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
  UPGRADE="$REPO_ROOT/plugins/security-assessment/commands/upgrade.md"
}

@test "security-assessment ships an upgrade.md command" {
  [ -f "$UPGRADE" ]
}

@test "security-assessment /upgrade frontmatter declares name=upgrade and user-invocable" {
  # YAML frontmatter is between the first two '---' lines.
  local frontmatter
  frontmatter=$(awk '/^---$/{c++; next} c==1' "$UPGRADE")
  echo "$frontmatter" | grep -qE '^name:[[:space:]]*upgrade$'
  echo "$frontmatter" | grep -qE '^user-invocable:[[:space:]]*true$'
}

@test "security-assessment /upgrade targets the correct plugin id" {
  # The Python detection block must pin PLUGIN to security-assessment.
  grep -qE 'PLUGIN[[:space:]]*=[[:space:]]*"security-assessment"' "$UPGRADE"
  # And the install/update commands must reference security-assessment, not dev-team.
  grep -q 'security-assessment@{marketplace}' "$UPGRADE"
}

@test "security-assessment /upgrade uses --scope on plugin update" {
  # Same scope-detection contract as dev-team's /upgrade — must not let
  # the CLI default to user-scope against a project-scope install.
  grep -qE 'claude plugin update --scope \{scope\} security-assessment@\{marketplace\}' "$UPGRADE"
}

@test "security-assessment /upgrade asks before enabling auto-update" {
  # No silent enablement: the consent prompt + yes-branch wording must be present.
  grep -qE 'Would you like to enable auto-update' "$UPGRADE"
  grep -qiE 'enable block.*run only if the user consents' "$UPGRADE"
}

@test "security-assessment /upgrade warns about marketplace-scope of auto-update flag" {
  # Auto-update is per-marketplace, not per-plugin — users must understand
  # consenting here also affects dev-team.
  grep -qiE 'marketplace-level' "$UPGRADE"
  grep -qE 'dev-team' "$UPGRADE"
}

@test "security-assessment /upgrade surfaces companion dependency check" {
  # If dev-team isn't installed, the user should be told.
  grep -qE '(dev-team@.* is not installed|claude plugin install --scope \{scope\} dev-team@\{marketplace\})' "$UPGRADE"
}

@test "security-assessment /upgrade prompts a restart" {
  grep -qE 'Restart Claude Code' "$UPGRADE"
}

@test "security-assessment /upgrade references the legacy deprecation stub" {
  # Documents the migration path for users coming from the pre-rename name.
  grep -qE 'agentic-security-assessment' "$UPGRADE"
}

@test "security-assessment /upgrade is registered in CLAUDE.md dispatch table" {
  local claude_md="$REPO_ROOT/plugins/security-assessment/CLAUDE.md"
  # Must appear in the dispatch registry table.
  grep -qE '\| \`/upgrade\` \|' "$claude_md"
  # And in the Commands list (count bumped from 4 to 5).
  grep -qE '\*\*Commands\*\* \(5\)' "$claude_md"
}

@test "security-assessment /upgrade is documented in README" {
  local readme="$REPO_ROOT/plugins/security-assessment/README.md"
  grep -qE '^## Update' "$readme"
  grep -qE '\| \`/upgrade\` \|' "$readme"
}
