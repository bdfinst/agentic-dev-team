#!/usr/bin/env bash
#
# SessionStart hook — install the dev-team plugin in EPHEMERAL environments.
#
# This is the single cloud/ephemeral installer (it replaced the older
# .claude/install-dev-team.sh). It prepares an ephemeral container so the app's
# tests/linters run AND the `dev-team@bfinster` plugin is ready to use:
#   1. Installs npm dependencies (if a package.json is present).
#   2. Ensures the dev-team plugin (+ its bfinster marketplace) is installed,
#      idempotently and time-boxed so it can never hang session start.
#   3. Runs the plugin's init-dev-team setup (jq, python3, Stryker, CodeGraph).
#
# GATE: runs only in an ephemeral session — when CLAUDE_CODE_REMOTE=true (set
# automatically by Claude Code on the web) OR DEV_TEAM_CLOUD_INSTALL=1 (manual
# opt-in, kept for back-compat). A no-op on local machines, where the plugin is
# already installed. Idempotent, non-interactive, and fail-open — never blocks
# session start.
#
# Progress goes to stderr (visible in logs, not added to context). stdout is
# reserved for the optional additionalContext guidance JSON (no-CLI case).
set -uo pipefail

log() { printf '[session-start] %s\n' "$*" >&2; }

# --- Gate: ephemeral sessions only ------------------------------------------
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ] && [ "${DEV_TEAM_CLOUD_INSTALL:-}" != "1" ]; then
  exit 0
fi

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$PROJECT_DIR" || exit 1

# --- 1. App dependencies ----------------------------------------------------
# Prefer `npm install` over `npm ci` so the cached container layer is reused.
if [ -f package.json ]; then
  log "Installing npm dependencies..."
  npm install >&2 2>&1 || log "npm install reported issues — continuing."
fi

# --- 2. Ensure the dev-team plugin is installed -----------------------------
# Time-box install steps so they can never hang session start. (A plugin
# installed at SessionStart takes effect on the NEXT session, not this one.)
_tmo() {
  if command -v timeout >/dev/null 2>&1; then timeout 120 "$@"
  elif command -v gtimeout >/dev/null 2>&1; then gtimeout 120 "$@"
  else "$@"; fi
}

if command -v claude >/dev/null 2>&1; then
  if claude plugin list 2>/dev/null | grep -qi 'dev-team'; then
    log "dev-team plugin already installed."
  else
    log "Ensuring dev-team@bfinster plugin is installed..."
    _tmo claude plugin marketplace add bdfinst/agentic-dev-team >/dev/null 2>&1 || true
    _tmo claude plugin install dev-team@bfinster >/dev/null 2>&1 || true
  fi
else
  # No CLI to install with: guide the user to the skill-file route. This is the
  # one place we write to stdout — a SessionStart additionalContext payload.
  cat <<'JSON'
{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"The dev-team plugin could not be installed in this ephemeral session (no `claude` CLI here). Run its workflows manually by reading the skill source and following it: plugins/dev-team/skills/<name>/SKILL.md (e.g. plan, code-review, build); agents at plugins/dev-team/agents/<name>.md. See CLAUDE.md -> Cloud sessions."}}
JSON
  log "No claude CLI — emitted skill-file guidance; skipping plugin install."
fi

# --- 3. Run the plugin's init-dev-team setup --------------------------------
# Locate the Linux replica of the init-dev-team skill. Prefer the cached
# marketplace; fall back to a shallow clone if it isn't present yet.
MARKET_DIR="$HOME/.claude/plugins/marketplaces/bfinster"
INIT_SCRIPT="$MARKET_DIR/init-dev-team-linux.sh"
PLUGIN_ROOT="$MARKET_DIR/plugins/dev-team"

if [ ! -f "$INIT_SCRIPT" ]; then
  log "Marketplace cache missing — cloning agentic-dev-team..."
  TMP_CLONE="$(mktemp -d)"
  if git clone --depth 1 https://github.com/bdfinst/agentic-dev-team "$TMP_CLONE" >/dev/null 2>&1; then
    INIT_SCRIPT="$TMP_CLONE/init-dev-team-linux.sh"
    PLUGIN_ROOT="$TMP_CLONE/plugins/dev-team"
  fi
fi

if [ -f "$INIT_SCRIPT" ]; then
  log "Running dev-team init..."
  # SKIP_PROBE: the model-availability probe needs ANTHROPIC_API_KEY and is
  # non-essential; skip it to keep startup output clean. Drop this to enable it.
  PLUGIN_ROOT="$PLUGIN_ROOT" SKIP_PROBE=1 bash "$INIT_SCRIPT" >&2 2>&1 \
    || log "dev-team init reported issues — continuing."
else
  log "Could not locate init-dev-team script — skipping plugin setup."
fi

log "Setup complete."
