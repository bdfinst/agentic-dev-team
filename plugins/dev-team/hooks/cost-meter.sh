#!/usr/bin/env bash
# cost-meter.sh — Stop / SubagentStop hook (issue #102).
#
# PostToolUse hooks carry no token usage, so this fires when a turn finishes,
# reads `transcript_path` from the hook payload, and records a per-session cost
# summary (tokens + dollars, by agent) to metrics/cost-metering.jsonl via
# hooks/lib/cost_meter.py. Token→cost uses knowledge/model-pricing.json.
#
# Posture: record-only and fail-open. Never blocks; any error → exit 0 silently.
# Opt-out: set DEV_TEAM_COST_METER=off to disable.

set -uo pipefail

input=$(cat)

[ "${DEV_TEAM_COST_METER:-on}" = "off" ] && exit 0

# Need jq + python3; if absent, no-op.
command -v jq >/dev/null 2>&1 || exit 0
command -v python3 >/dev/null 2>&1 || exit 0

echo "$input" | jq -e . >/dev/null 2>&1 || exit 0

transcript=$(echo "$input" | jq -r '.transcript_path // empty')
[ -z "$transcript" ] || [ ! -f "$transcript" ] && exit 0

cwd=$(echo "$input" | jq -r '.cwd // empty')
[ -n "$cwd" ] && [ -d "$cwd" ] || cwd="$PWD"

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
log="${cwd}/metrics/cost-metering.jsonl"

python3 "${HOOK_DIR}/lib/cost_meter.py" record \
  --transcript "$transcript" --log "$log" >/dev/null 2>&1 || true

exit 0
