#!/usr/bin/env bash
# model-probe.sh — opt-in probe of $ANTHROPIC_BASE_URL/v1/models.
#
# Reads a y/N answer from stdin. On "y", probes the Anthropic endpoint
# and writes .claude/model-overrides.json only when a default tier is
# missing. Skipped automatically on non-Anthropic hosts (Bedrock, Vertex,
# proxies that don't speak the Anthropic /v1/models shape).
#
# Called by /init-dev-team. Standalone-testable; the curl shim under
# tests/hooks/fake-bin/curl deterministically replays the failure modes.
#
# Env vars (TEST-ONLY injection seams):
#   MODEL_ROUTING_JSON       defaults to <plugin>/knowledge/model-routing.json
#   MODEL_OVERRIDES_JSON     defaults to .claude/model-overrides.json
#   MODEL_PROBE_CURL_SENTINEL  fake-bin curl touches this on invocation;
#                              tests assert presence/absence
#   MODEL_PROBE_TIMEOUT      defaults to 5 (seconds)
#
# Exit code is always 0 — the probe is a convenience, not a gate.

set -uo pipefail

_resolve_paths() {
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  : "${MODEL_ROUTING_JSON:="${script_dir}/../../knowledge/model-routing.json"}"
  : "${MODEL_OVERRIDES_JSON:=".claude/model-overrides.json"}"
  : "${MODEL_PROBE_TIMEOUT:=5}"
}

# Return the host portion of $1 (URL), or empty string if not parseable.
_host_from_url() {
  echo "$1" | sed -E 's|^https?://||; s|/.*$||; s|:[0-9]+$||'
}

# Is the host a supported Anthropic endpoint shape?
_is_anthropic_host() {
  local host="$1"
  case "$host" in
    ""|api.anthropic.com)
      return 0 ;;
    *.anthropic.com)
      return 0 ;;
    *)
      return 1 ;;
  esac
}

# Read y/N from stdin. Returns 0 on "y"/"Y", 1 otherwise.
_read_yn() {
  local answer
  read -r answer || answer=""
  case "$answer" in
    y|Y|yes|YES) return 0 ;;
    *)           return 1 ;;
  esac
}

# Run the probe. Echoes user-visible messages on stdout/stderr; never
# fails the calling /init-dev-team flow.
_run_probe() {
  local base_url host
  base_url="${ANTHROPIC_BASE_URL:-}"
  host=$(_host_from_url "$base_url")

  if ! _is_anthropic_host "$host"; then
    echo "Probe skipped: $host is not a supported Anthropic endpoint." >&2
    echo "  See docs/model-routing.md for Bedrock/Vertex setup." >&2
    return 0
  fi

  local probe_url="${base_url:-https://api.anthropic.com}/v1/models"
  local response status_code

  # Request status code separately so we can branch on HTTP failures
  # without requiring curl --fail (which would mask the 500 body fixture).
  status_code=$(curl -s -o /dev/null -w '%{http_code}' --max-time "$MODEL_PROBE_TIMEOUT" "$probe_url" 2>/dev/null)
  local curl_status=$?

  if [[ "$curl_status" -eq 28 ]]; then
    echo "Probe timed out after ${MODEL_PROBE_TIMEOUT}s: $probe_url" >&2
    echo "Dispatch fallback still applies; see docs/model-routing.md." >&2
    return 0
  fi

  if [[ "$curl_status" -ne 0 ]]; then
    echo "Probe failed (curl exit $curl_status): $probe_url" >&2
    echo "Dispatch fallback still applies; see docs/model-routing.md." >&2
    return 0
  fi

  if [[ "$status_code" != "200" ]]; then
    echo "Probe endpoint returned HTTP $status_code: $probe_url" >&2
    echo "Dispatch fallback still applies; see docs/model-routing.md." >&2
    return 0
  fi

  # Fetch the body and parse.
  response=$(curl -s --max-time "$MODEL_PROBE_TIMEOUT" "$probe_url" 2>/dev/null)
  if ! echo "$response" | jq -e '.data' >/dev/null 2>&1; then
    echo "Probe response was not valid JSON: $probe_url" >&2
    echo "Dispatch fallback still applies; see docs/model-routing.md." >&2
    return 0
  fi

  _diff_against_routing "$response"
}

# Compare returned model IDs against routing.json. If a default is
# missing, write overrides; else announce success.
_diff_against_routing() {
  local response="$1"
  local available_ids
  available_ids=$(echo "$response" | jq -r '.data[].id' | sort)

  local haiku_id sonnet_id opus_id
  haiku_id=$(jq -r '.haiku' "$MODEL_ROUTING_JSON")
  sonnet_id=$(jq -r '.sonnet' "$MODEL_ROUTING_JSON")
  opus_id=$(jq -r '.opus' "$MODEL_ROUTING_JSON")

  local missing_haiku=0
  echo "$available_ids" | grep -qxF "$haiku_id" || missing_haiku=1

  if [[ "$missing_haiku" -eq 0 ]]; then
    echo "All model tiers available; no overrides needed."
    return 0
  fi

  _write_overrides "$response"
  echo "Model tier 'haiku' bumped to 'sonnet'; .claude/model-overrides.json written."
}

_write_overrides() {
  local response="$1"
  local generated_at
  generated_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  mkdir -p "$(dirname "$MODEL_OVERRIDES_JSON")"
  echo "$response" | jq \
    --arg ts "$generated_at" \
    --arg reason "haiku snapshot not in /v1/models response" \
    '{
       tier_aliases: { haiku: "sonnet" },
       generated_at: $ts,
       available_models: [.data[].id],
       reason: $reason
     }' > "$MODEL_OVERRIDES_JSON"
}

main() {
  _resolve_paths
  if ! _read_yn; then
    # Declined → no-op.
    return 0
  fi
  _run_probe
}

main "$@"
