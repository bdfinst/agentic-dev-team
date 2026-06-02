#!/usr/bin/env bash
# phase-timer.sh — phase-start/phase-end event emitter for /security-assessment.
#
# Appends one JSONL record per invocation to
# <memory-dir>/phase-timings-<slug>.jsonl. Records carry event/phase/slug/
# epoch_ms/iso/pid and let the exec-report-generator reconstruct wall-time
# per phase and surface drift from intended parallelism.
#
# Conventions: matches style of check-severity-consistency.sh + verify-report.sh,
# with two deliberate deviations documented in the companion plan's PR:
#   1. `set -euo pipefail` (stricter errexit vs. existing `set -uo pipefail`).
#   2. Four-value exit-code contract (0/1/2/3) vs. existing 0/1/3 — distinguishes
#      missing-input from malformed-input so callers can branch programmatically.
#
# Usage:
#   phase-timer.sh start <phase-name> <slug> [<memory-dir>]
#   phase-timer.sh end   <phase-name> <slug> [<memory-dir>]
#   phase-timer.sh -h | --help
#
# Inputs:
#   <phase-name>  Phase identifier (e.g. phase-1-tool-pass). Free-form string.
#   <slug>        Target slug used to derive the output file name.
#   <memory-dir>  Optional; defaults to ./memory. Must be writable.
#
# Output:
#   Appends one JSONL record to <memory-dir>/phase-timings-<slug>.jsonl:
#     {"event":"start|end","phase":"...","slug":"...",
#      "epoch_ms":1745528439123,"iso":"2026-04-24T17:30:39.123Z","pid":12345}
#
# Exit codes:
#   0   record appended successfully
#   1   runtime error (memory-dir not writable, jq/python3 failure, etc.)
#   2   (unused by this script; reserved in the family contract for missing required input)
#   3   bad usage (unknown mode, missing argument)

set -euo pipefail

# shellcheck source-path=SCRIPTDIR
# shellcheck source=./_lib.sh
source "$(dirname "$0")/_lib.sh"

usage() {
  cat <<'USAGE'
usage: phase-timer.sh start|end <phase-name> <slug> [<memory-dir>]

Appends one JSONL record to <memory-dir>/phase-timings-<slug>.jsonl.
<memory-dir> defaults to ./memory.

Exit codes:
  0  success
  1  runtime error (e.g. unwritable memory-dir)
  2  (reserved; unused by phase-timer.sh — see helper-script family contract)
  3  bad usage (missing argument or unknown mode)
USAGE
}

if [[ $# -eq 0 ]]; then
  usage >&2
  exit 3
fi

lib_parse_help "$@"

if [[ $# -lt 3 ]]; then
  usage >&2
  exit 3
fi

EVENT="$1"
PHASE="$2"
SLUG="$3"
MEMORY_DIR="${4:-./memory}"

case "$EVENT" in
  start|end) ;;
  *)
    echo "phase-timer.sh: unknown mode '$EVENT' (expected 'start' or 'end')" >&2
    usage >&2
    exit 3
    ;;
esac

# Ensure memory-dir exists and is writable. If mkdir fails (e.g. the parent
# is read-only) or if an existing dir isn't writable, diagnose and exit 1.
if [[ -e "$MEMORY_DIR" && ! -d "$MEMORY_DIR" ]]; then
  echo "phase-timer.sh: $MEMORY_DIR exists but is not a directory" >&2
  exit 1
fi

if ! mkdir -p "$MEMORY_DIR" 2>/dev/null; then
  echo "phase-timer.sh: cannot create memory-dir $MEMORY_DIR" >&2
  exit 1
fi

if [[ ! -w "$MEMORY_DIR" ]]; then
  echo "phase-timer.sh: cannot write to $MEMORY_DIR (permission denied)" >&2
  exit 1
fi

OUT="$MEMORY_DIR/phase-timings-$SLUG.jsonl"

# Millisecond epoch + ISO-8601 timestamp via _lib.sh helpers. python3
# fallback ensures portability across macOS BSD date and GNU date.
EPOCH_MS="$(lib_epoch_ms)" || {
  echo "phase-timer.sh: failed to obtain millisecond timestamp" >&2
  exit 1
}
ISO="$(lib_iso_now milliseconds)" || {
  echo "phase-timer.sh: failed to format ISO-8601 timestamp" >&2
  exit 1
}

# Compose the record via jq so strings are escaped correctly.
RECORD="$(jq -c -n \
  --arg event "$EVENT" \
  --arg phase "$PHASE" \
  --arg slug "$SLUG" \
  --argjson epoch_ms "$EPOCH_MS" \
  --arg iso "$ISO" \
  --argjson pid "$$" \
  '{event:$event,phase:$phase,slug:$slug,epoch_ms:$epoch_ms,iso:$iso,pid:$pid}')" || {
  echo "phase-timer.sh: jq failed to compose record" >&2
  exit 1
}

printf '%s\n' "$RECORD" >> "$OUT"
