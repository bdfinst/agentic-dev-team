#!/usr/bin/env bash
# SessionStart hook (registered in .claude/settings.json): if CodeGraph,
# Repowise, or Graphify are already installed but this checkout has never
# been indexed (e.g. a freshly created worktree, or a fresh clone on a
# machine that already has the CLIs globally installed), build the keyless
# index automatically. This never installs a missing CLI — that stays an
# explicit /project-init or /setup opt-in, per
# knowledge/codegraph-vs-graphify.md ("None is guaranteed to be present").
#
# Fail-open and time-boxed — never blocks session start.
set -uo pipefail

_root="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$_root" || exit 0

_tmo() {
  local secs="$1"
  shift
  if command -v timeout >/dev/null 2>&1; then
    timeout "$secs" "$@"
  elif command -v gtimeout >/dev/null 2>&1; then
    gtimeout "$secs" "$@"
  else
    "$@"
  fi
}

_cache="${HOME}/.cache"
mkdir -p "$_cache"

_notes=()

# CodeGraph — installed but not initialized in this checkout.
if command -v codegraph >/dev/null 2>&1 && [ ! -d .codegraph ]; then
  if _tmo 60 codegraph init . >"$_cache/codegraph-sessionstart.log" 2>&1; then
    _notes+=("CodeGraph: initialized .codegraph/ (was missing in this checkout).")
  else
    _notes+=("CodeGraph: init failed or timed out — see ~/.cache/codegraph-sessionstart.log.")
  fi
fi

# Repowise — installed but not indexed in this checkout. Keyless, no LLM cost.
# `repowise init` also writes its own usage-instructions block straight into
# the TRACKED .claude/CLAUDE.md (REPOWISE:START/END markers) — snapshot and
# restore that file so the hook only leaves the gitignored .repowise/ index
# behind, matching how it treats CodeGraph/Graphify (index-only, no tracked
# file writes).
if command -v repowise >/dev/null 2>&1 && [ ! -d .repowise ]; then
  _claude_md=".claude/CLAUDE.md"
  _claude_md_snapshot=""
  if [ -f "$_claude_md" ]; then
    _claude_md_snapshot="$_cache/CLAUDE.md.pre-repowise-sessionstart"
    cp "$_claude_md" "$_claude_md_snapshot"
  fi
  if _tmo 120 repowise init --index-only >"$_cache/repowise-sessionstart.log" 2>&1; then
    _notes+=("Repowise: built the keyless index (was missing in this checkout).")
  else
    _notes+=("Repowise: index failed or timed out — see ~/.cache/repowise-sessionstart.log.")
  fi
  if [ -n "$_claude_md_snapshot" ]; then
    cp "$_claude_md_snapshot" "$_claude_md"
    rm -f "$_claude_md_snapshot"
  fi
fi

# Graphify — installed but no graph built yet in this checkout. `update`
# handles both a first build and an incremental refresh; keyless (AST-only).
if command -v graphify >/dev/null 2>&1 && [ ! -f graphify-out/graph.json ]; then
  if _tmo 240 graphify update . >"$_cache/graphify-sessionstart.log" 2>&1; then
    _notes+=("Graphify: built graphify-out/graph.json (was missing in this checkout).")
  else
    _notes+=("Graphify: build failed or timed out — see ~/.cache/graphify-sessionstart.log.")
  fi
fi

if [ "${#_notes[@]}" -gt 0 ]; then
  python3 -c "
import json, sys
notes = sys.argv[1:]
print(json.dumps({'hookSpecificOutput': {'hookEventName': 'SessionStart', 'additionalContext': ' '.join(notes)}}))
" "${_notes[@]}"
fi
exit 0
