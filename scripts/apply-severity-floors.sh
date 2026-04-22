#!/usr/bin/env bash
# apply-severity-floors.sh — wrapper for Phase 2b severity calibration.
#
# Invoked by /security-assessment after Phase 2 (fp-reduction) has written
# memory/disposition-<slug>.json. Applies domain-class severity floors by
# rule_id pattern, rewrites the register, and emits an audit log.
#
# Usage:
#   apply-severity-floors.sh <slug> [<memory-dir>]
#
# Defaults:
#   memory-dir = ./memory

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SCRIPT_DIR/lib/apply_severity_floors.py"

SLUG="${1:?usage: apply-severity-floors.sh <slug> [<memory-dir>]}"
MEMORY="${2:-$(pwd)/memory}"

DISPOSITION="$MEMORY/disposition-$SLUG.json"
AUDIT="$MEMORY/severity-floors-log-$SLUG.jsonl"

if [[ ! -f "$DISPOSITION" ]]; then
  echo "note: no disposition file at $DISPOSITION; skipping Phase 2b"
  exit 0
fi

python3 "$LIB" \
  --disposition "$DISPOSITION" \
  --audit-log-out "$AUDIT"
