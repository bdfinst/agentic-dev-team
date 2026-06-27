#!/usr/bin/env bash
# skills-index.sh — Claude Code PostToolUse hook on Edit|Write.
#
# When an Edit or Write touches a skill definition (skills/<name>/SKILL.md),
# regenerate plugins/dev-team/docs/skills.md by shelling out to
# hooks/lib/build-skills-index.sh. The catalog is derived from each SKILL.md's
# `name`/`description` frontmatter, so editing a skill keeps the catalog current
# with no manual step. A CI freshness gate (--check) is the strict net behind it.
#
# Sibling of knowledge-index.sh (which rebuilds knowledge/index.json); kept
# separate so each index has its own trigger, builder, and test seam rather than
# entangling two artifacts in one hook.
#
# Posture: fail-open. Any internal error (missing builder, jq absent, malformed
# stdin, builder non-zero exit) → exit 0 with a single `[skills-index]`-tagged
# stderr line. The hook must never block an Edit.
#
# Feedback: `[skills-index] rebuilt` on success, `[skills-index] rebuild failed:
# <reason>` on failure. Silent when the touched file is not a SKILL.md.
#
# Input:  JSON on stdin (PostToolUse contract: tool_name, tool_input.file_path).
# Output: Stderr feedback when a SKILL.md is touched; otherwise silent. Exit 0.
#
# Env vars (TEST-ONLY injection seam):
#   SKILLS_INDEX_BUILDER  override the builder path. Production callers must NOT
#                         set this — it is resolved from the hook's own location.

set -uo pipefail

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILDER="${SKILLS_INDEX_BUILDER:-${HOOK_DIR}/lib/build-skills-index.sh}"

main() {
  local input
  input=$(cat)

  # Fail-open on malformed input.
  if ! echo "$input" | jq -e . >/dev/null 2>&1; then
    return 0
  fi

  local tool_name file_path
  tool_name=$(echo "$input" | jq -r '.tool_name // empty')
  file_path=$(echo "$input" | jq -r '.tool_input.file_path // empty')

  case "$tool_name" in
    Edit|Write) ;;
    *) return 0 ;;
  esac

  # Only a skill definition affects the catalog.
  if [[ ! "$file_path" =~ /?plugins/dev-team/skills/[^/]+/SKILL\.md$ ]]; then
    return 0
  fi

  local stderr_file
  stderr_file=$(mktemp)
  if bash "$BUILDER" >/dev/null 2>"$stderr_file"; then
    echo "[skills-index] rebuilt" >&2
  else
    local reason
    reason=$(head -n 1 "$stderr_file" 2>/dev/null || echo "unknown")
    echo "[skills-index] rebuild failed: $reason" >&2
  fi
  rm -f "$stderr_file"
  return 0
}

main
