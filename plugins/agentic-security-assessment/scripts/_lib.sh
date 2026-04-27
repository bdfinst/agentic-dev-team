#!/usr/bin/env bash
# _lib.sh — shared helpers for the Phase-0/1c/2b helper scripts.
#
# Sourced (not executed) by phase-timer.sh, find-ci-files.sh,
# apply-severity-floors.sh, and apply-accepted-risks.sh. Extraction was
# triggered by the "3+ identical helpers verbatim" rule (see
# plans/security-assessment-helper-scripts.md Step 5 refactor).
#
# Callers must define their own `usage()` function (each script's usage
# text is unique) and invoke `lib_parse_help "$@"` at entry to honor
# -h / --help uniformly across the family.
#
# This file is sourced — no shebang-exec path is expected.

# Exit-code contract shared across the helper-script family:
#   0  success
#   1  runtime error
#   2  missing required input
#   3  bad usage OR malformed input

# lib_parse_help — if the first positional is -h or --help, print
# usage() to stdout and exit 0. Otherwise no-op.
# Callers must define usage() before sourcing or before the first call.
lib_parse_help() {
  case "${1:-}" in
    -h|--help)
      usage
      exit 0
      ;;
  esac
}

# lib_iso_now — prints the current UTC time in ISO-8601 with the
# chosen precision. Portable across macOS (BSD date) and Linux (GNU
# date) via python3 stdlib, which this plugin already depends on.
# Usage: lib_iso_now [milliseconds|seconds]   (default: milliseconds)
lib_iso_now() {
  local precision="${1:-milliseconds}"
  python3 -c "
from datetime import datetime, timezone
print(datetime.now(timezone.utc).isoformat(timespec='$precision').replace('+00:00','Z'))
"
}

# lib_epoch_ms — prints the current Unix epoch in milliseconds.
# Tries GNU `date +%s%3N` first; falls back to python3 if the BSD
# `date` on the host doesn't support %3N.
lib_epoch_ms() {
  local ts
  if ts="$(date +%s%3N 2>/dev/null)" && [[ "$ts" =~ ^[0-9]{13}$ ]]; then
    printf '%s' "$ts"
  else
    python3 -c 'import time;print(int(time.time()*1000))'
  fi
}
