#!/usr/bin/env bash
# knowledge-index.sh — Claude Code PostToolUse hook on Edit|Write.
#
# When an Edit or Write touches a file in the indexed corpus
# (knowledge/*.md or skills/*/SKILL.md, excluding knowledge/schemas/),
# regenerate plugins/agentic-dev-team/knowledge/index.json by shelling
# out to hooks/lib/build-knowledge-index.sh.
#
# Posture: fail-open. Any internal error (missing builder, jq absent,
# malformed stdin, builder non-zero exit) → exit 0 with a single
# `[knowledge-index]`-tagged stderr line. The hook must never block an
# Edit, no matter what goes wrong during the rebuild.
#
# Feedback: on success, emits `[knowledge-index] rebuilt` to stderr so
# users see one short confirmation line per regeneration. On failure,
# emits `[knowledge-index] rebuild failed: <reason>`.
#
# Input:  JSON on stdin (Claude Code PostToolUse contract: tool_name,
#         tool_input.file_path).
# Output: Stderr feedback when the corpus is touched; otherwise silent.
#         Exit 0 always.
#
# Env vars (TEST-ONLY injection seams):
#   KNOWLEDGE_INDEX_BUILDER  override the builder path. Production callers
#                            must NOT set this — the builder is resolved
#                            from the hook's own location via BASH_SOURCE.

set -uo pipefail

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/knowledge-index-paths.sh
source "${HOOK_DIR}/lib/knowledge-index-paths.sh"
BUILDER="${KNOWLEDGE_INDEX_BUILDER:-${HOOK_DIR}/lib/build-knowledge-index.sh}"

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

  # Only act on Edit and Write.
  case "$tool_name" in
    Edit|Write) ;;
    *) return 0 ;;
  esac

  # Missing or out-of-corpus path → silent no-op.
  if [[ -z "$file_path" ]]; then
    return 0
  fi
  if ! _is_corpus_path "$file_path"; then
    return 0
  fi

  # Rebuild. Capture stderr so we can summarize on failure.
  local stderr_file
  stderr_file=$(mktemp)
  if bash "$BUILDER" >/dev/null 2>"$stderr_file"; then
    echo "[knowledge-index] rebuilt" >&2
  else
    local reason
    reason=$(head -n 1 "$stderr_file" 2>/dev/null || echo "unknown")
    echo "[knowledge-index] rebuild failed: $reason" >&2
  fi
  rm -f "$stderr_file"
  return 0
}

main
