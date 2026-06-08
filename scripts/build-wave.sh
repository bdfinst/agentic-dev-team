#!/usr/bin/env bash
# build-wave.sh — the build's wave schedule, derived from plan-waves.sh.
#
# Emits the ordered waves with their members and a deterministic reconcile order
# (members sorted) so a wave merges reproducibly regardless of completion order:
#
#   { "schema": "build-wave/v1",
#     "waves": [ { "wave": 1, "members": [...], "reconcile_order": [...] } ],
#     "collisions": [...] }
#
# Exits non-zero if the plan is invalid (cycle / missing / unknown — surfaced by
# plan-waves.sh) OR if any wave has a declared same-file collision: a wave with a
# collision must not be built concurrently, so the build refuses it here.
#
# Usage: build-wave.sh <plan.md>

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

FILE="${1:-}"
{ [ -n "$FILE" ] && [ -f "$FILE" ]; } || { echo "usage: build-wave.sh <plan.md>" >&2; exit 2; }

# plan-waves.sh exits non-zero (and prints) on cycle/missing/unknown; pipefail
# propagates that. jq reshapes the waves into the build schedule.
waves_json="$("$HERE/plan-waves.sh" "$FILE")" || exit $?

echo "$waves_json" | jq '{
  schema: "build-wave/v1",
  waves: [ .waves | to_entries[] | {
    wave: (.key + 1),
    members: .value,
    reconcile_order: (.value | sort)
  } ],
  collisions: .collisions
}'

# Refuse a schedule that contains a same-wave file collision.
if [ "$(echo "$waves_json" | jq '.collisions | length')" -gt 0 ]; then
  echo "build-wave: same-wave file collision(s) — cannot build this wave concurrently:" >&2
  echo "$waves_json" | jq -r '.collisions[] | "  wave \(.wave): \(.slices|join(" + ")) both touch \(.file)"' >&2
  exit 1
fi
