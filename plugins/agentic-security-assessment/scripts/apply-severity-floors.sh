#!/usr/bin/env bash
# apply-severity-floors.sh — deterministic Phase 2b severity-floor application.
#
# For each entry in <memory-dir>/disposition-<slug>.json whose
# exploitability.rationale embeds the pattern "<class> floor=<n>" and whose
# class appears in knowledge/severity-floors.json's recognized_classes,
# raises exploitability.score to max(original, floor) and appends a log
# record to <memory-dir>/severity-floors-log-<slug>.jsonl.
#
# Phase ordering: must run after fp-reduction (Phase 2) and before
# narrative/compliance (Phase 3). Callers MUST serialize invocations;
# atomicity of the <path>.tmp + mv handles the single-writer-but-crash
# case; concurrent writers are a contract violation.
#
# Idempotency: after applying a floor, the script sets
# exploitability.floor_applied=true on the entry; subsequent runs skip
# marked entries. Re-running against an already-floored register produces
# no new log records and no disposition changes.
#
# Suppression: entries whose rationale contains "floor=<n> suppressed to <m>"
# are skipped entirely (the fp-reduction agent signaled that the default
# floor does not apply in this context).
#
# Conventions: matches style of check-severity-consistency.sh + verify-report.sh,
# with the two deliberate deviations documented in phase-timer.sh:
#   1. set -euo pipefail (stricter errexit).
#   2. Four-value exit-code contract (0/1/2/3).
#
# Usage:
#   apply-severity-floors.sh <slug> [<memory-dir>]
#   apply-severity-floors.sh -h | --help
#
# Inputs:
#   <memory-dir>/disposition-<slug>.json  — the disposition register (required)
#   knowledge/severity-floors.json        — recognized-class allow-list (required)
#
# Outputs:
#   <memory-dir>/severity-floors-log-<slug>.jsonl  — one JSONL record per floor applied
#   <memory-dir>/disposition-<slug>.json           — mutated in-place (atomic rewrite)
#
# Log record schema (per 2026-04-24 reference):
#   {"id":<entry-id>,"floor_class":<class>,"floor":<int>,
#    "original_score":<int>,"final_score":<int>}
#
# Exit codes:
#   0   success (zero or more floors applied)
#   1   runtime error (jq/python3 failure, malformed disposition JSON)
#   2   disposition-<slug>.json not found
#   3   bad usage (missing argument)

set -euo pipefail

# shellcheck source-path=SCRIPTDIR
# shellcheck source=./_lib.sh
source "$(dirname "$0")/_lib.sh"

usage() {
  cat <<'USAGE'
usage: apply-severity-floors.sh <slug> [<memory-dir>]

Applies domain-class severity floors to <memory-dir>/disposition-<slug>.json
in place and appends JSONL records to <memory-dir>/severity-floors-log-<slug>.jsonl.
<memory-dir> defaults to ./memory.

Exit codes:
  0  success
  1  runtime error (malformed JSON, tool failure)
  2  disposition-<slug>.json not found
  3  bad usage (missing argument)
USAGE
}

if [[ $# -eq 0 ]]; then
  usage >&2
  exit 3
fi

lib_parse_help "$@"

SLUG="$1"
MEMORY_DIR="${2:-./memory}"

DISP="$MEMORY_DIR/disposition-$SLUG.json"
LOG="$MEMORY_DIR/severity-floors-log-$SLUG.jsonl"

if [[ ! -f "$DISP" ]]; then
  echo "apply-severity-floors.sh: disposition-$SLUG.json not found at $DISP" >&2
  exit 2
fi

# Locate the recognized-classes list. The plugin root is two levels above
# scripts/ (plugin-root/scripts/apply-severity-floors.sh).
PLUGIN_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FLOORS_FILE="$PLUGIN_ROOT/knowledge/severity-floors.json"

if [[ ! -f "$FLOORS_FILE" ]]; then
  echo "apply-severity-floors.sh: knowledge/severity-floors.json not found at $FLOORS_FILE" >&2
  exit 1
fi

# Extract the allow-list of recognized class names as a newline-separated
# string. `jq` is a hard dependency of this plugin (already used elsewhere).
RECOGNIZED_CLASSES="$(jq -r '.recognized_classes[].class' "$FLOORS_FILE")" || {
  echo "apply-severity-floors.sh: failed to read recognized_classes from $FLOORS_FILE" >&2
  exit 1
}

# Python handles the disposition mutation + log emission. Stdlib only (json, re).
DISP_TMP="$DISP.tmp"

set +e
python3 - "$DISP" "$DISP_TMP" "$LOG" "$RECOGNIZED_CLASSES" <<'PY'
import json
import re
import sys

disp_path, disp_tmp, log_path, classes_blob = sys.argv[1:5]
recognized = {c for c in classes_blob.split('\n') if c.strip()}

try:
    with open(disp_path) as f:
        disp = json.load(f)
except json.JSONDecodeError as e:
    print(f"apply-severity-floors.sh: malformed JSON in {disp_path}: {e}", file=sys.stderr)
    sys.exit(1)

if not isinstance(disp, dict) or 'entries' not in disp:
    print(f"apply-severity-floors.sh: {disp_path} missing 'entries' key", file=sys.stderr)
    sys.exit(1)

# Patterns
FLOOR_PAT = re.compile(r'([a-z][a-z-]*)\s+floor=(\d+)')
SUPPRESS_PAT = re.compile(r'floor=\d+\s+suppressed\s+to\s+\d+')

new_log_lines = []
for entry in disp['entries']:
    expl = entry.get('exploitability')
    if not isinstance(expl, dict):
        continue
    # Idempotency: skip already-floored entries.
    if expl.get('floor_applied') is True:
        continue
    rationale = expl.get('rationale') or ''
    # Suppression phrase overrides default floor.
    if SUPPRESS_PAT.search(rationale):
        continue
    m = FLOOR_PAT.search(rationale)
    if not m:
        continue
    floor_class, floor_str = m.group(1), m.group(2)
    if floor_class not in recognized:
        continue
    floor = int(floor_str)
    original = int(expl.get('score', 0))
    final = max(original, floor)
    # Mutate in place.
    expl['score'] = final
    expl['floor_applied'] = True
    # Log record.
    new_log_lines.append(json.dumps({
        'id': entry.get('id'),
        'floor_class': floor_class,
        'floor': floor,
        'original_score': original,
        'final_score': final,
    }, separators=(',', ':')))

# Atomic write of the disposition register.
with open(disp_tmp, 'w') as f:
    json.dump(disp, f, indent=2)
    f.write('\n')

# Append new log records.
if new_log_lines:
    with open(log_path, 'a') as f:
        for line in new_log_lines:
            f.write(line + '\n')
PY
PY_RC=$?
set -e

if [[ $PY_RC -ne 0 ]]; then
  rm -f "$DISP_TMP"
  echo "apply-severity-floors.sh: python3 floor-application failed (rc=$PY_RC)" >&2
  exit 1
fi

# Commit the atomic rewrite.
mv "$DISP_TMP" "$DISP"
