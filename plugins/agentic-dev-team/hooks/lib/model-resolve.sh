#!/usr/bin/env bash
# model-resolve.sh — pre-dispatch tier → snapshot resolver.
#
# Reads knowledge/model-routing.json (required) and .claude/model-overrides.json
# (optional) and prints the resolved Anthropic snapshot for a requested tier
# on stdout. On any tier bump (alias applied), appends one JSONL event to
# .claude/metrics/model-routing.log.
#
# Called by:
#   - hooks/agent-model-resolve.sh (PreToolUse hook on the Agent matcher)
#   - commands/model-routing-check.md (via --dump-map)
#
# Usage:
#   model-resolve.sh <tier> [--caller <name>]
#   model-resolve.sh --dump-map           # (added in Step 7; not yet)
#
# Env vars (TEST-ONLY injection seams — do not document as user-facing):
#   MODEL_ROUTING_JSON     defaults to <plugin>/knowledge/model-routing.json
#   MODEL_OVERRIDES_JSON   defaults to .claude/model-overrides.json
#   MODEL_BUMP_LOG         defaults to .claude/metrics/model-routing.log
#
# Exit codes:
#   0 — resolved
#   2 — unknown tier or missing tier argument (caller error)
#   3 — exhausted / cycle (resolver cannot satisfy request) — added Step 5/6
#   4 — knowledge/model-routing.json missing — added Step 6
#   5 — overrides file is not valid JSON — added Step 6

set -uo pipefail

# ---------------------------------------------------------------------------
# _resolve_paths — populate the three input/output paths with defaults if the
# corresponding env vars aren't set. Test isolation hinges on these env vars.
# ---------------------------------------------------------------------------
_resolve_paths() {
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  : "${MODEL_ROUTING_JSON:="${script_dir}/../../knowledge/model-routing.json"}"
  : "${MODEL_OVERRIDES_JSON:=".claude/model-overrides.json"}"
  : "${MODEL_BUMP_LOG:=".claude/metrics/model-routing.log"}"
}

# ---------------------------------------------------------------------------
# Validate that <tier> is one of haiku|sonnet|opus.
# ---------------------------------------------------------------------------
_is_valid_tier() {
  case "$1" in
    haiku|sonnet|opus) return 0 ;;
    *) return 1 ;;
  esac
}

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
main() {
  if [[ $# -lt 1 ]]; then
    echo "Usage: model-resolve.sh <tier> [--caller <name>]" >&2
    echo "Valid tiers: haiku, sonnet, opus" >&2
    return 2
  fi

  local tier="$1"

  if ! _is_valid_tier "$tier"; then
    echo "Unknown tier '$tier'. Valid tiers: haiku, sonnet, opus." >&2
    return 2
  fi

  _resolve_paths

  # Happy path: read the snapshot directly from routing.json.
  # Override / cascade / error handling is added in Steps 4–6 — including
  # the routing.json-missing and key-missing cases. Until those land, fall
  # through with exit 1 (generic) rather than exit 3 (which is reserved for
  # the exhaustion/cycle templates added in Step 6).
  local snapshot
  snapshot=$(jq -r --arg t "$tier" '.[$t] // empty' "$MODEL_ROUTING_JSON")
  if [[ -z "$snapshot" ]]; then
    echo "Internal: no snapshot for tier '$tier' in $MODEL_ROUTING_JSON (routing.json is malformed; see Step 6)" >&2
    return 1
  fi

  echo "$snapshot"
}

main "$@"
