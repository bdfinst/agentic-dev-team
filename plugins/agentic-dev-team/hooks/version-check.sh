#!/usr/bin/env bash
# version-check.sh — Claude Code PostToolUse hook
#
# Checks once per day whether the plugin repo has upstream updates.
# If updates are available, prints a notice suggesting /upgrade.
#
# Input:  JSON on stdin (ignored)
# Output: Update notice on stdout, or nothing if up-to-date
# Cache:  /tmp/adt-version-check-<date> prevents repeated checks

set -uo pipefail

# Consume stdin (required by hook protocol)
cat > /dev/null

# ── Daily cache: skip if already checked today ───────────────────────────────
TODAY=$(date +%Y-%m-%d)
CACHE_FILE="/tmp/adt-version-check-${TODAY}"

if [ -f "$CACHE_FILE" ]; then
  # Already checked today — replay cached message if any
  CACHED=$(cat "$CACHE_FILE")
  [ -n "$CACHED" ] && echo "$CACHED"
  exit 0
fi

# ── Locate plugin git repo (one level up from hooks/) ────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if ! git -C "$PLUGIN_DIR" rev-parse --is-inside-work-tree &>/dev/null; then
  # Not a git repo (vendored copy) — skip silently
  touch "$CACHE_FILE"
  exit 0
fi

# ── Fetch quietly with a short timeout ───────────────────────────────────────
# Use background process + wait to implement timeout (works on macOS and Linux)
git -C "$PLUGIN_DIR" fetch origin --quiet 2>/dev/null &
FETCH_PID=$!
SECONDS=0
while kill -0 "$FETCH_PID" 2>/dev/null; do
  if [ "$SECONDS" -ge 5 ]; then
    kill "$FETCH_PID" 2>/dev/null
    wait "$FETCH_PID" 2>/dev/null
    # Network too slow — skip silently, don't cache so it retries later
    exit 0
  fi
  sleep 1
done
wait "$FETCH_PID" 2>/dev/null
FETCH_EXIT=$?
if [ "$FETCH_EXIT" -ne 0 ]; then
  # Fetch failed — skip silently, don't cache so it retries later
  exit 0
fi

# ── Compare HEAD to origin/main ──────────────────────────────────────────────
DEFAULT_BRANCH=$(git -C "$PLUGIN_DIR" symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||')
DEFAULT_BRANCH="${DEFAULT_BRANCH:-main}"

BEHIND=$(git -C "$PLUGIN_DIR" rev-list --count "HEAD..origin/${DEFAULT_BRANCH}" 2>/dev/null || echo "0")

if [ "$BEHIND" -gt 0 ]; then
  MSG="📦 agentic-dev-team: ${BEHIND} update(s) available. Run /upgrade to update."
  echo "$MSG" > "$CACHE_FILE"
  echo "$MSG"
else
  # Up to date — cache empty result
  touch "$CACHE_FILE"
fi

exit 0
