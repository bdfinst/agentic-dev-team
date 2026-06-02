#!/usr/bin/env bash
# overrides-banner.sh — Claude Code SessionStart hook.
#
# Surfaces a single-line note to stderr when .claude/model-overrides.json
# exists at session start, so users behind restricted endpoints (corporate
# proxies, Bedrock, Vertex) know tier bumps may be silently happening.
#
# Markdown command bodies cannot deterministically emit terminal output;
# this SessionStart hook is the enforcement surface for AC19. Without it,
# the only way to discover an active override is to run /model-routing-check
# proactively.
#
# Input:  JSON on stdin (SessionStart contract: hook_event_name, cwd, ...)
# Output: Banner text on stderr when overrides file exists, nothing otherwise.
#         Exit 0 always — a buggy banner hook must never block a session.

set -uo pipefail

BANNER='Note: model routing overrides active — run /model-routing-check to review.'

main() {
  local input
  input=$(cat)

  # Fail-open on malformed input.
  if ! echo "$input" | jq -e . >/dev/null 2>&1; then
    return 0
  fi

  local overrides_path="${MODEL_OVERRIDES_JSON:-.claude/model-overrides.json}"
  if [[ -f "$overrides_path" ]]; then
    echo "$BANNER" >&2
  fi
  return 0
}

main
