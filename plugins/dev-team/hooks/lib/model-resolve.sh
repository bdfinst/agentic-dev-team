#!/usr/bin/env bash
# model-resolve.sh — pre-dispatch effort band → model resolver.
#
# Maps an effort band (low|medium|high) to an Anthropic model using:
#   1. an optional ordered ladder at .claude/model-ladder.json — a JSON array
#      of model IDs from least to most capable — via
#      index = round_half_up(weight·(N−1)) with weights low=0, medium=0.5,
#      high=1; OR
#   2. the shipped default map in knowledge/model-routing.json, used whenever
#      no ladder exists or the ladder is malformed/empty.
#
# Legacy tier aliases (haiku|sonnet|opus) are accepted for the migration
# window and normalized to bands (haiku→low, sonnet→medium, opus→high).
#
# A missing or malformed ladder degrades to the default map and never aborts
# dispatch. This resolver does NOT log routing bumps — the dispatch hook
# (agent-model-resolve.sh) owns that single site, so there is no double-log.
#
# Called by:
#   - hooks/agent-model-resolve.sh (PreToolUse hook on the Agent matcher)
#   - skills/model-routing-check/SKILL.md (via --dump-map)
#
# Usage:
#   model-resolve.sh <band|tier> [--caller <name>]
#   model-resolve.sh --dump-map
#
# Env vars (TEST-ONLY injection seams — do not document as user-facing):
#   MODEL_ROUTING_JSON   defaults to <plugin>/knowledge/model-routing.json
#   MODEL_LADDER_JSON    defaults to .claude/model-ladder.json
#
# Exit codes:
#   0 — resolved
#   2 — unknown band/tier or missing argument (caller error)
#   4 — knowledge/model-routing.json missing
#
# Note: the legacy deny-relevant exits (3 exhausted/cycle, 5 malformed
# overrides) are no longer reachable — band resolution always succeeds once
# routing.json is present, because a bad ladder degrades to the default map.

set -uo pipefail

# ---------------------------------------------------------------------------
# _resolve_paths — populate input paths with defaults if env vars aren't set.
# Test isolation hinges on these env vars.
# ---------------------------------------------------------------------------
_resolve_paths() {
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  : "${MODEL_ROUTING_JSON:="${script_dir}/../../knowledge/model-routing.json"}"
  : "${MODEL_LADDER_JSON:=".claude/model-ladder.json"}"
}

# ---------------------------------------------------------------------------
# _normalize_band — map a band or legacy tier to a canonical band.
# Echoes "" for an unrecognized token.
# ---------------------------------------------------------------------------
_normalize_band() {
  case "$1" in
    low|haiku)     echo "low" ;;
    medium|sonnet) echo "medium" ;;
    high|opus)     echo "high" ;;
    *)             echo "" ;;
  esac
}

# ---------------------------------------------------------------------------
# _band_weight — the ladder weight for a band (low=0, medium=0.5, high=1).
# ---------------------------------------------------------------------------
_band_weight() {
  case "$1" in
    low)    echo "0" ;;
    medium) echo "0.5" ;;
    high)   echo "1" ;;
  esac
}

# ---------------------------------------------------------------------------
# _die_missing_routing — the one surviving fatal case (exit 4).
# ---------------------------------------------------------------------------
_die_missing_routing() {
  cat >&2 <<EOF
Model routing file missing: ${MODEL_ROUTING_JSON}
  This file ships with the plugin and must be present.
  Restore with: git checkout knowledge/model-routing.json
EOF
  return 4
}

# ---------------------------------------------------------------------------
# _ladder_is_valid — true iff the ladder file exists and is a non-empty JSON
# array of strings. Anything else degrades to the default map.
# ---------------------------------------------------------------------------
_ladder_is_valid() {
  [[ -e "$MODEL_LADDER_JSON" ]] || return 1
  jq -e 'type == "array" and length > 0 and all(.[]; type == "string")' \
    "$MODEL_LADDER_JSON" >/dev/null 2>&1
}

# ---------------------------------------------------------------------------
# _default_for_band — the shipped default snapshot for a band.
# ---------------------------------------------------------------------------
_default_for_band() {
  jq -r --arg b "$1" '.[$b] // empty' "$MODEL_ROUTING_JSON"
}

# ---------------------------------------------------------------------------
# _resolve_band — map a canonical band to a model: ladder when valid, else
# the shipped default map.
# ---------------------------------------------------------------------------
_resolve_band() {
  local band="$1"
  if _ladder_is_valid; then
    local n weight rounding idx
    n=$(jq 'length' "$MODEL_LADDER_JSON")
    weight=$(_band_weight "$band")
    # The rounding convention is pinned in model-routing.json (.rounding) so
    # the formula has a single source of truth. Only round_half_up exists.
    rounding=$(jq -r '.rounding // "round_half_up"' "$MODEL_ROUTING_JSON" 2>/dev/null)
    idx=$(awk -v w="$weight" -v n="$n" -v mode="$rounding" 'BEGIN {
      # round_half_up(weight·(N−1)) == floor(weight·(N−1) + 0.5) for w ≥ 0.
      printf "%d", int(w * (n - 1) + 0.5)
    }')
    jq -r --argjson i "$idx" '.[$i]' "$MODEL_LADDER_JSON"
    return 0
  fi
  _default_for_band "$band"
}

# ---------------------------------------------------------------------------
# _dump_map — pretty-print the effective band → model map. Used by
# /model-routing-check.
# ---------------------------------------------------------------------------
_dump_map() {
  local band
  for band in low medium high; do
    printf '  %-7s → %s\n' "$band" "$(_resolve_band "$band")"
  done
}

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
main() {
  if [[ $# -lt 1 ]]; then
    echo "Usage: model-resolve.sh <band> [--caller <name>]" >&2
    echo "       model-resolve.sh --dump-map" >&2
    echo "Valid bands: low, medium, high" >&2
    return 2
  fi

  _resolve_paths

  # All paths require routing.json — fail early with the proper template.
  if [[ ! -f "$MODEL_ROUTING_JSON" ]]; then
    _die_missing_routing
    return 4
  fi

  # --dump-map mode
  if [[ "$1" == "--dump-map" ]]; then
    _dump_map
    return $?
  fi

  local requested="$1"
  shift

  local band
  band="$(_normalize_band "$requested")"
  if [[ -z "$band" ]]; then
    echo "Unknown effort band '$requested'. Valid bands: low, medium, high (legacy tiers haiku, sonnet, opus accepted)." >&2
    return 2
  fi

  # Parse optional --caller flag. Accepted but ignored: the dispatch hook
  # owns bump logging, so the resolver no longer needs the caller name.
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --caller)
        shift
        [[ $# -gt 0 ]] && shift
        ;;
      *)
        echo "Unknown argument: $1" >&2
        return 2
        ;;
    esac
  done

  _resolve_band "$band"
}

main "$@"
