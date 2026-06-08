#!/usr/bin/env bash
# build-jobs.sh — resolve the effective build concurrency for a wave.
#
#   effective = min(requested --jobs, DEV_TEAM_MAX_PARALLEL_BUILDS, wave width)
#
# A requested value or max that is zero, negative, or non-integer clamps to 1
# (deterministic, never an error). The max defaults to 2 when the env var is
# unset. `--jobs 1` therefore resolves to 1 — the sequential decision. Prints the
# effective integer on stdout and a human-readable resolution line on stderr.
#
# Usage: build-jobs.sh --wave-width W [--jobs N]

set -uo pipefail

JOBS=""; WIDTH=""
while [ $# -gt 0 ]; do
  case "$1" in
    --jobs)       JOBS="${2:-}"; shift 2 ;;
    --wave-width) WIDTH="${2:-}"; shift 2 ;;
    *) echo "usage: build-jobs.sh --wave-width W [--jobs N]" >&2; exit 2 ;;
  esac
done

# A positive integer stays; anything else (empty, 0, negative, non-numeric) -> 1.
norm() {
  case "$1" in
    ''|*[!0-9]*) echo 1 ;;
    *) if [ "$1" -ge 1 ] 2>/dev/null; then echo "$1"; else echo 1; fi ;;
  esac
}

max="$(norm "${DEV_TEAM_MAX_PARALLEL_BUILDS:-2}")"
width="$(norm "${WIDTH:-1}")"
# An unset --jobs means "as parallel as allowed": default to the max.
jobs="$(norm "${JOBS:-$max}")"

eff="$jobs"
[ "$max" -lt "$eff" ] && eff="$max"
[ "$width" -lt "$eff" ] && eff="$width"

echo "build-jobs: requested=${JOBS:-(unset)} max=${max} wave_width=${width} -> effective=${eff}" >&2
echo "$eff"
