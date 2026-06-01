#!/usr/bin/env bash
# model-resolve.sh — pre-dispatch tier → snapshot resolver.
#
# Reads knowledge/model-routing.json (required) and .claude/model-overrides.json
# (optional), walks any alias chain in `tier_aliases`, and prints the resolved
# Anthropic snapshot on stdout. On any tier bump (requested ≠ served), appends
# exactly one JSONL event to the bump log per invocation — intermediate hops
# in a multi-hop chain do not log separately.
#
# Called by:
#   - hooks/agent-model-resolve.sh (PreToolUse hook on the Agent matcher)
#   - commands/model-routing-check.md (via --dump-map)
#
# Usage:
#   model-resolve.sh <tier> [--caller <name>]
#   model-resolve.sh --dump-map
#
# Env vars (TEST-ONLY injection seams — do not document as user-facing):
#   MODEL_ROUTING_JSON     defaults to <plugin>/knowledge/model-routing.json
#   MODEL_OVERRIDES_JSON   defaults to .claude/model-overrides.json
#   MODEL_BUMP_LOG         defaults to .claude/metrics/model-routing.log
#
# Exit codes:
#   0 — resolved
#   1 — internal error (e.g., routing.json malformed in an unexpected way)
#   2 — unknown tier or missing tier argument (caller error)
#   3 — exhausted / cycle (resolver cannot satisfy request)
#   4 — knowledge/model-routing.json missing
#   5 — overrides file is not valid JSON

set -uo pipefail

_MAX_HOPS=3  # haiku → sonnet → opus is the longest legitimate chain.

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

_is_valid_tier() {
  case "$1" in
    haiku|sonnet|opus) return 0 ;;
    *) return 1 ;;
  esac
}

# ---------------------------------------------------------------------------
# _die_exhausted — Stderr template for the top-tier-exhaustion case (AC5).
# ---------------------------------------------------------------------------
_die_exhausted() {
  local requested="$1" override_entry="$2"
  cat >&2 <<EOF
All model tiers exhausted for requested tier '${requested}'.
  Routing defaults: ${MODEL_ROUTING_JSON}
  Override entry:   ${override_entry}   (from ${MODEL_OVERRIDES_JSON})
  Run /model-routing-check to inspect resolved state and recent bumps.
EOF
  return 3
}

# ---------------------------------------------------------------------------
# _die_cycle — Stderr template for cycle detection (AC5a).
# ---------------------------------------------------------------------------
_die_cycle() {
  local chain="$1"
  cat >&2 <<EOF
Cycle detected in tier aliases: ${chain}
  Override file:    ${MODEL_OVERRIDES_JSON}
  Edit the file to remove the cycle, or delete it to restore defaults.
  Run /model-routing-check after editing.
EOF
  return 3
}

# ---------------------------------------------------------------------------
# _die_missing_routing — AC5b.
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
# _die_malformed_overrides — AC5c.
# ---------------------------------------------------------------------------
_die_malformed_overrides() {
  cat >&2 <<EOF
Override file is not valid JSON: ${MODEL_OVERRIDES_JSON}
  Delete the file to restore default routing, or fix the JSON and re-run.
  Run /model-routing-check after editing.
EOF
  return 5
}

# ---------------------------------------------------------------------------
# _load_aliases — print the JSON object of tier_aliases (or "{}" when no
# overrides file exists). Exits 5 via _die_malformed_overrides on parse fail.
# ---------------------------------------------------------------------------
_load_aliases() {
  if [[ ! -e "$MODEL_OVERRIDES_JSON" ]]; then
    echo "{}"
    return 0
  fi
  # Validate JSON parseable
  if ! jq -e . "$MODEL_OVERRIDES_JSON" >/dev/null 2>&1; then
    _die_malformed_overrides
    return $?
  fi
  jq -c '.tier_aliases // {}' "$MODEL_OVERRIDES_JSON"
}

# ---------------------------------------------------------------------------
# _cascade — walk the alias chain from a starting tier.
# Args: starting_tier aliases_json
# Echoes the final tier (or "unavailable" sentinel) on stdout, and the
# visited chain on stderr-but-captured. Returns 3 on cycle (via _die_cycle),
# 0 otherwise.
# ---------------------------------------------------------------------------
_cascade() {
  local current="$1" aliases="$2"
  local -a visited=()
  local hops=0
  while (( hops < _MAX_HOPS )); do
    # Cycle check: have we already visited "$current"?
    # ${visited[@]+"${visited[@]}"} expansion is empty-array-safe under `set -u`.
    local v
    for v in ${visited[@]+"${visited[@]}"}; do
      if [[ "$v" == "$current" ]]; then
        local chain="${visited[*]} ${current}"
        # Format chain with arrows for readability
        chain="$(printf '%s' "$chain" | tr ' ' ',' | sed 's/,/ → /g')"
        _die_cycle "$chain"
        return 3
      fi
    done
    visited+=("$current")

    # Look up alias for "current".
    local next
    next=$(echo "$aliases" | jq -r --arg t "$current" '.[$t] // empty')
    if [[ -z "$next" ]]; then
      # No alias for current → it's the terminal tier.
      echo "$current"
      return 0
    fi
    current="$next"
    hops=$((hops + 1))
  done
  # Exceeded max hops without termination — treat as cycle.
  local chain="${visited[*]} ${current}"
  chain="$(printf '%s' "$chain" | tr ' ' ',' | sed 's/,/ → /g')"
  _die_cycle "$chain"
  return 3
}

# ---------------------------------------------------------------------------
# _log_bump — append exactly one JSONL line per invocation. Idempotent on
# bump-log directory creation.
# Args: requested served reason caller
# ---------------------------------------------------------------------------
_log_bump() {
  local requested="$1" served="$2" reason="$3" caller="${4:-}"
  mkdir -p "$(dirname "$MODEL_BUMP_LOG")"
  local ts
  ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  jq -nc \
    --arg ts "$ts" \
    --arg requested "$requested" \
    --arg served "$served" \
    --arg reason "$reason" \
    --arg caller "$caller" \
    '{ts: $ts, requested: $requested, served: $served, reason: $reason, caller: $caller}' \
    >> "$MODEL_BUMP_LOG"
}

# ---------------------------------------------------------------------------
# _resolve_tier — top-level resolve for one tier.
# Echoes the snapshot on stdout. On bump, appends to the log.
# ---------------------------------------------------------------------------
_resolve_tier() {
  local requested="$1" caller="${2:-}"

  # Fast path: when no overrides file exists, skip the alias machinery
  # entirely and resolve in one jq invocation. This is the dominant case
  # for users on a standard Anthropic key and is hit on every dispatch,
  # so the savings compound (AC15 perf gate).
  if [[ ! -e "$MODEL_OVERRIDES_JSON" ]]; then
    jq -r --arg t "$requested" '.[$t]' "$MODEL_ROUTING_JSON"
    return 0
  fi

  local aliases
  aliases=$(_load_aliases) || return $?

  local final
  final=$(_cascade "$requested" "$aliases") || return $?

  # final may be a known tier OR a sentinel (e.g., "unavailable") OR an
  # unknown string that hand-edited overrides introduced.
  local snapshot
  snapshot=$(jq -r --arg t "$final" '.[$t] // empty' "$MODEL_ROUTING_JSON")
  if [[ -z "$snapshot" ]]; then
    # Find the override entry for the requested tier (or the first step in
    # the chain that pointed at the unresolvable terminal) for the error msg.
    local override_entry
    override_entry=$(echo "$aliases" | jq -r \
      --arg req "$requested" --arg final "$final" \
      'to_entries | map(select(.value == $final or .key == $req)) | .[0] | "\"\(.key)\": \"\(.value)\""' \
      2>/dev/null || echo "(unknown)")
    _die_exhausted "$requested" "$override_entry"
    return 3
  fi

  if [[ "$final" != "$requested" ]]; then
    _log_bump "$requested" "$final" "override" "$caller"
  fi
  echo "$snapshot"
}

# ---------------------------------------------------------------------------
# _dump_map — pretty-print the effective tier → snapshot map (Step 7).
# Used by /model-routing-check.
# ---------------------------------------------------------------------------
_dump_map() {
  local aliases
  aliases=$(_load_aliases) || return $?
  local tier
  for tier in haiku sonnet opus; do
    local final snapshot
    final=$(_cascade "$tier" "$aliases" 2>/dev/null) || final="$tier"
    snapshot=$(jq -r --arg t "$final" '.[$t] // "(unavailable)"' "$MODEL_ROUTING_JSON")
    printf '  %-7s → %s\n' "$tier" "$snapshot"
  done
}

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
main() {
  if [[ $# -lt 1 ]]; then
    echo "Usage: model-resolve.sh <tier> [--caller <name>]" >&2
    echo "       model-resolve.sh --dump-map" >&2
    echo "Valid tiers: haiku, sonnet, opus" >&2
    return 2
  fi

  _resolve_paths

  # All paths require routing.json — fail early with the proper template.
  if [[ ! -f "$MODEL_ROUTING_JSON" ]]; then
    _die_missing_routing
    return 4
  fi

  # --dump-map mode (Step 7)
  if [[ "$1" == "--dump-map" ]]; then
    _dump_map
    return $?
  fi

  local tier="$1"
  shift

  if ! _is_valid_tier "$tier"; then
    echo "Unknown tier '$tier'. Valid tiers: haiku, sonnet, opus." >&2
    return 2
  fi

  # Parse optional --caller flag
  local caller=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --caller)
        caller="${2:-}"
        shift 2
        ;;
      *)
        echo "Unknown argument: $1" >&2
        return 2
        ;;
    esac
  done

  _resolve_tier "$tier" "$caller"
}

main "$@"
