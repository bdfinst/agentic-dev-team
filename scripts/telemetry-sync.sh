#!/usr/bin/env bash
# telemetry-sync.sh — push this machine's session digest to the telemetry
# "database" repo and pull everyone else's (Delta D, #178).
#
# The repo is treated like a DATABASE, not code: each machine owns one
# append-only file (digests/<host>/session-digest.jsonl), writes are direct to
# the default branch (no PR), and per-host filenames make merges conflict-free.
# See docs/telemetry-repo-security.md for the access model.
#
# Config resolution (first match wins):
#   1. $DEV_TEAM_TELEMETRY_REMOTE                      (a git URL)
#   2. ~/.claude/.dev-team/telemetry.json  ->  .remote
# Optional:
#   $DEV_TEAM_TELEMETRY_CLONE  local working clone  (default ~/.claude/.dev-team/agent-telemetry)
#   $DEV_TEAM_TELEMETRY_HOST   host label           (default: hostname -s)
#   .clone / .host in the config file are honored too.
#
# Usage:
#   telemetry-sync.sh --check    validate config only; exit 3 if not configured
#   telemetry-sync.sh            extract -> commit -> pull --rebase -> push
#
# Exit codes: 0 ok, 2 missing tool, 3 not configured, 4 transport/git error.

set -uo pipefail

CONFIG="${DEV_TEAM_TELEMETRY_CONFIG:-$HOME/.claude/.dev-team/telemetry.json}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

_cfg() {  # _cfg <key> — read a key from the JSON config, empty if absent
  [ -f "$CONFIG" ] && command -v jq >/dev/null 2>&1 || return 0
  jq -r --arg k "$1" '.[$k] // empty' "$CONFIG" 2>/dev/null
}

# --- resolve config --------------------------------------------------------
REMOTE="${DEV_TEAM_TELEMETRY_REMOTE:-$(_cfg remote)}"
if [ -z "$REMOTE" ]; then
  echo "No telemetry repository configured." >&2
  echo "Configure it one of two ways:" >&2
  echo "  - export DEV_TEAM_TELEMETRY_REMOTE=git@github.com:<owner>/<repo>.git" >&2
  echo "  - or write {\"remote\": \"git@github.com:<owner>/<repo>.git\"} to $CONFIG" >&2
  echo "(The /session-review skill will prompt you and write this for you.)" >&2
  echo "Setup + security: plugins/dev-team/docs/telemetry-repo-security.md" >&2
  exit 3
fi

CLONE="${DEV_TEAM_TELEMETRY_CLONE:-$(_cfg clone)}"
CLONE="${CLONE:-$HOME/.claude/.dev-team/agent-telemetry}"
HOST="${DEV_TEAM_TELEMETRY_HOST:-$(_cfg host)}"
HOST="${HOST:-$(hostname -s 2>/dev/null || echo unknown-host)}"

if [ "${1:-}" = "--check" ]; then
  echo "telemetry remote: $REMOTE"
  echo "local clone:      $CLONE"
  echo "host label:       $HOST"
  exit 0
fi

for t in git python3; do
  command -v "$t" >/dev/null 2>&1 || { echo "missing required tool: $t" >&2; exit 2; }
done

# --- ensure a local clone of the data repo ---------------------------------
if [ ! -d "$CLONE/.git" ]; then
  mkdir -p "$(dirname "$CLONE")"
  git clone --quiet "$REMOTE" "$CLONE" || { echo "clone failed: $REMOTE" >&2; exit 4; }
fi
git -C "$CLONE" pull --rebase --quiet || { echo "pull --rebase failed" >&2; exit 4; }

# --- extract new/changed sessions into this host's append-only file --------
DIGEST_DIR="$CLONE/digests/$HOST"
mkdir -p "$DIGEST_DIR"
WM="$HOME/.claude/.dev-team/telemetry-sync.json"
mkdir -p "$(dirname "$WM")"
python3 "$SCRIPT_DIR/session_extract.py" \
  --sync-out "$DIGEST_DIR/session-digest.jsonl" \
  --watermark "$WM" --host "$HOST" \
  --plugin-root "$SCRIPT_DIR/../plugins/dev-team" \
  || { echo "extract failed" >&2; exit 4; }

# --- commit + push (direct to default branch; it's a database) -------------
if [ -z "$(git -C "$CLONE" status --porcelain)" ]; then
  echo "no new sessions to sync for $HOST"
  exit 0
fi
git -C "$CLONE" add -A
git -C "$CLONE" -c user.name="dev-team telemetry" \
  -c user.email="telemetry@dev-team.local" \
  commit --quiet -m "telemetry: $HOST $(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  || { echo "commit failed" >&2; exit 4; }
git -C "$CLONE" pull --rebase --quiet || { echo "rebase before push failed" >&2; exit 4; }
git -C "$CLONE" push --quiet || { echo "push failed" >&2; exit 4; }
echo "synced digest for $HOST -> $REMOTE"
