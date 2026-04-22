#!/usr/bin/env bash
# phase-timer.sh — record phase start/end timestamps to memory/phase-timings-<slug>.jsonl.
#
# Pipeline phases call this helper at their start and end. The resulting
# JSONL file gives the exec-report-generator an audit trail of:
#   - what actually ran (vs. what was intended)
#   - how long each phase took
#   - which phases overlapped (i.e. were genuinely parallel)
#
# Usage:
#   scripts/phase-timer.sh start <phase-name> <slug> [<memory-dir>]
#   scripts/phase-timer.sh end <phase-name> <slug> [<memory-dir>]
#   scripts/phase-timer.sh run <phase-name> <slug> -- <command> [<args>...]
#
# The `run` form wraps a command: records start, runs the command, records
# end (with exit code). This is the ergonomic form for shell pipelines.
#
# The JSONL format:
#   {"ts":"2026-04-22T13:00:00Z","event":"start","phase":"phase-1-tool-first","pid":12345}
#   {"ts":"2026-04-22T13:02:30Z","event":"end","phase":"phase-1-tool-first","duration_seconds":150,"exit_code":0,"pid":12345}
#
# Exit codes:
#   0  — recording succeeded (or command succeeded in `run` mode)
#   N  — command's exit code in `run` mode

set -uo pipefail

usage() {
  cat <<'EOF'
usage:
  phase-timer.sh start <phase-name> <slug> [<memory-dir>]
  phase-timer.sh end   <phase-name> <slug> [<memory-dir>]
  phase-timer.sh run   <phase-name> <slug> -- <command> [<args>...]
  phase-timer.sh run   <phase-name> <slug> <memory-dir> -- <command> [<args>...]

Writes to: <memory-dir>/phase-timings-<slug>.jsonl  (default memory-dir: ./memory)
EOF
}

if [[ $# -lt 3 ]]; then
  usage >&2
  exit 2
fi

MODE="$1"; shift
PHASE="$1"; shift
SLUG="$1"; shift

# Optional memory-dir positional (before `--` in `run` mode)
MEMORY="$(pwd)/memory"
if [[ $# -gt 0 && "$1" != "--" ]]; then
  MEMORY="$1"; shift
fi

mkdir -p "$MEMORY"
TIMINGS="$MEMORY/phase-timings-$SLUG.jsonl"

now_iso() { date -u +%Y-%m-%dT%H:%M:%SZ; }
now_epoch() { date -u +%s; }

record_start() {
  local ts epoch
  ts=$(now_iso)
  epoch=$(now_epoch)
  printf '{"ts":"%s","epoch":%d,"event":"start","phase":"%s","pid":%d}\n' \
    "$ts" "$epoch" "$PHASE" "$$" >> "$TIMINGS"
  echo "$epoch"
}

record_end() {
  local start_epoch="$1" exit_code="$2"
  local ts end_epoch duration
  ts=$(now_iso)
  end_epoch=$(now_epoch)
  duration=$((end_epoch - start_epoch))
  printf '{"ts":"%s","epoch":%d,"event":"end","phase":"%s","duration_seconds":%d,"exit_code":%d,"pid":%d}\n' \
    "$ts" "$end_epoch" "$PHASE" "$duration" "$exit_code" "$$" >> "$TIMINGS"
}

case "$MODE" in
  start)
    record_start >/dev/null
    ;;
  end)
    # Look up the most recent `start` record for this phase to compute duration.
    start_epoch=""
    if [[ -f "$TIMINGS" ]]; then
      # Find the last "start" line for this phase; extract its epoch.
      start_epoch=$(grep "\"event\":\"start\",\"phase\":\"$PHASE\"" "$TIMINGS" 2>/dev/null | tail -1 | \
        sed -n 's/.*"epoch":\([0-9]*\).*/\1/p' || true)
    fi
    end_epoch=$(now_epoch)
    if [[ -n "$start_epoch" ]]; then
      duration=$((end_epoch - start_epoch))
    else
      duration=0
    fi
    printf '{"ts":"%s","epoch":%d,"event":"end","phase":"%s","duration_seconds":%d,"exit_code":0,"pid":%d}\n' \
      "$(now_iso)" "$end_epoch" "$PHASE" "$duration" "$$" >> "$TIMINGS"
    ;;
  run)
    # Strip the -- delimiter
    if [[ $# -gt 0 && "$1" == "--" ]]; then shift; fi
    if [[ $# -eq 0 ]]; then
      echo "error: 'run' mode requires a command after --" >&2
      usage >&2
      exit 2
    fi
    start_epoch=$(record_start)
    "$@"
    rc=$?
    record_end "$start_epoch" "$rc"
    exit "$rc"
    ;;
  *)
    echo "error: unknown mode '$MODE'" >&2
    usage >&2
    exit 2
    ;;
esac
