#!/usr/bin/env bash
# build-worktree-baseref.sh — detect the effective worktree.baseRef setting
# so /build can warn loudly (never mutate) when it is not "head".
#
# Issue #553 / plans/build-worktree-inherits-caller-head.md Slice 1.
#
# Background: Claude Code's `worktree.baseRef: "head"` setting makes
# isolation:"worktree" Agent-tool dispatch branch child worktrees from the
# caller's local HEAD instead of origin/<default> ("fresh", the default).
# docs/spikes/worktree-baseref-head-spike.md empirically confirmed this
# setting is honored only at project (.claude/settings.json) and user
# (~/.claude/settings.json) scope — NOT at project-local
# (.claude/settings.local.json) or plugin (plugins/<name>/settings.json)
# scope. This script's default search order reflects only the two scopes
# that are actually honored; it intentionally does not consult the
# project-local or plugin files as authoritative sources.
#
# Usage:
#   build-worktree-baseref.sh detect
#
# Prints exactly one token to stdout and always exits 0
# (degrade-never-abort, mirroring hooks/lib/model-resolve.sh's precedent):
#   head    — effective setting is "head"
#   fresh   — effective setting is "fresh"
#   unset   — no honored settings file sets worktree.baseRef
#   unknown — detection failed (e.g. jq unavailable) — treat as fail-safe
#
# Env vars (TEST-ONLY injection seam — do not document as user-facing):
#   BASEREF_SETTINGS_PATHS   colon-separated list of settings files,
#                            highest precedence first. Defaults to
#                            ".claude/settings.json:$HOME/.claude/settings.json".

set -uo pipefail

# ---------------------------------------------------------------------------
# _default_settings_paths — the real precedence order per the Slice 0 spike:
# project scope, then user scope. Colon-separated to match the
# BASEREF_SETTINGS_PATHS seam's format.
# ---------------------------------------------------------------------------
_default_settings_paths() {
  printf '%s' ".claude/settings.json:${HOME:-}/.claude/settings.json"
}

# ---------------------------------------------------------------------------
# _settings_paths — BASEREF_SETTINGS_PATHS if set, else the real default.
# ---------------------------------------------------------------------------
_settings_paths() {
  if [ -n "${BASEREF_SETTINGS_PATHS:-}" ]; then
    printf '%s' "$BASEREF_SETTINGS_PATHS"
  else
    _default_settings_paths
  fi
}

# ---------------------------------------------------------------------------
# _detect — walk the settings files in precedence order. The first file
# that both parses as valid JSON and has a non-empty .worktree.baseRef of
# "head" or "fresh" wins. A file that fails to parse is skipped (falls
# through to the next, lower-precedence file) rather than aborting the
# whole detection. Prints "unset" if every readable/parseable file lacks
# the key. Prints "unknown" (without reading any file) if jq itself is
# unavailable — detection cannot be trusted without it.
# ---------------------------------------------------------------------------
_detect() {
  if ! command -v jq >/dev/null 2>&1; then
    echo "unknown"
    return 0
  fi

  local paths oldifs f val rc
  paths="$(_settings_paths)"

  oldifs="$IFS"
  IFS=':'
  # shellcheck disable=SC2086 # intentional word-splitting on IFS=':' to
  # turn the colon-separated path list into positional args.
  set -- $paths
  IFS="$oldifs"

  for f in "$@"; do
    [ -n "$f" ] || continue
    [ -f "$f" ] || continue

    val="$(jq -r '.worktree.baseRef // empty' "$f" 2>/dev/null)"
    rc=$?
    if [ "$rc" -ne 0 ]; then
      # Malformed JSON (or any jq failure) — skip this file, try the next.
      continue
    fi

    case "$val" in
      head)  echo "head";  return 0 ;;
      fresh) echo "fresh"; return 0 ;;
    esac
  done

  echo "unset"
  return 0
}

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
main() {
  case "${1:-}" in
    detect)
      _detect
      ;;
    *)
      echo "Usage: build-worktree-baseref.sh detect" >&2
      return 2
      ;;
  esac
}

main "$@"
