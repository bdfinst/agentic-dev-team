#!/usr/bin/env bash
# SessionStart hook (registered in .claude/settings.json): make the dev-team
# plugin available in CLOUD sessions only.
#
# FALLBACK PATH, NOT THE PRIMARY ONE. This hook runs AFTER Claude has booted and
# enumerated its skills/agents/commands, so a plugin it installs cannot load into
# the CURRENT session — it only takes effect on the NEXT one. To load the plugin
# in the same session, install it from the environment Setup script instead (it
# runs pre-boot); see docs/cloud-setup.md. Keep this hook for environments where
# editing the Setup script isn't possible.
#
# CLOUD-ONLY GATE: this is a no-op unless DEV_TEAM_CLOUD_INSTALL=1 is set. Set
# that variable in your Claude Code web environment (Environment settings ->
# Environment variables). Do NOT set it locally — so local sessions, where the
# plugin is already installed, are never touched by this hook.
#
# In a gated (cloud) session it tries to install the plugin if the `claude` CLI
# is present; if the CLI is absent (cloud VMs may not ship it), it emits guidance
# to run the plugin's workflows from its skill files instead. Fail-open — never
# blocks session start.
set -uo pipefail

# Local (or any session without the cloud flag): do nothing.
[ "${DEV_TEAM_CLOUD_INSTALL:-}" = "1" ] || exit 0

# Cloud, but no CLI to install with: guide to the skill-file route.
if ! command -v claude >/dev/null 2>&1; then
  cat <<'JSON'
{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"The dev-team plugin could not be installed in this cloud session (no `claude` CLI here). Run its workflows manually by reading the skill source and following it: plugins/dev-team/skills/<name>/SKILL.md (e.g. plan, code-review, build); agents at plugins/dev-team/agents/<name>.md. See CLAUDE.md -> Cloud sessions."}}
JSON
  exit 0
fi

# Install AND refresh, time-boxed so it can never hang session start. We do NOT
# no-op when the plugin is already present: a reused environment snapshot pins
# whatever version installed first, so every session must re-pull the marketplace
# catalog and upgrade. (A SessionStart install/upgrade takes effect on the NEXT
# session; enabling auto-update below refreshes at launch to close that gap.)
_tmo() {
  if command -v timeout >/dev/null 2>&1; then timeout 120 "$@"
  elif command -v gtimeout >/dev/null 2>&1; then gtimeout 120 "$@"
  else "$@"; fi
}
_tmo claude plugin marketplace add    bdfinst/agentic-dev-team >/dev/null 2>&1 || true
_tmo claude plugin marketplace update bfinster                 >/dev/null 2>&1 || true
_tmo claude plugin install dev-team@bfinster                   >/dev/null 2>&1 || true
_tmo claude plugin update  dev-team@bfinster                   >/dev/null 2>&1 || true
python3 "$(dirname "$0")/enable-plugin-autoupdate.py" >/dev/null 2>&1 || true
exit 0
