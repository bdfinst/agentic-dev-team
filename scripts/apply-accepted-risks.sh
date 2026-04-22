#!/usr/bin/env bash
# apply-accepted-risks.sh — wrapper for the Phase 1c suppression gate.
#
# Invoked by /security-assessment after Phase 1 + 1b have populated
# findings-<slug>.jsonl. Parses ACCEPTED-RISKS.md at the target root
# (if present), applies first-match-wins suppression, rewrites the
# findings JSONL in place, and emits suppressed-*.jsonl +
# suppression-log-*.jsonl.
#
# Usage:
#   apply-accepted-risks.sh <target-dir> <slug> [<memory-dir>]
#
# Defaults:
#   memory-dir = ./memory
#
# Exit codes:
#   0   success
#   2   schema-invalid ACCEPTED-RISKS.md
#   3   missing required inputs

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SCRIPT_DIR/lib/apply_accepted_risks.py"

TARGET="${1:?usage: apply-accepted-risks.sh <target-dir> <slug> [<memory-dir>]}"
SLUG="${2:?slug required}"
MEMORY="${3:-$(pwd)/memory}"

# Auto-record phase timing — works even if the LLM orchestrator forgets to
# bracket the invocation per commands/security-assessment.md § Phase timing.
TIMER="$SCRIPT_DIR/phase-timer.sh"
PHASE="phase-1c-accepted-risks"
if [[ -x "$TIMER" ]]; then
  "$TIMER" start "$PHASE" "$SLUG" "$MEMORY" 2>/dev/null || true
  # Always record end, even on failure
  trap '"$TIMER" end "$PHASE" "$SLUG" "$MEMORY" 2>/dev/null || true' EXIT
fi

if [[ ! -d "$TARGET" ]]; then
  echo "error: target not a directory: $TARGET" >&2
  exit 3
fi

FINDINGS="$MEMORY/findings-$SLUG.jsonl"
SUPPRESSED="$MEMORY/suppressed-$SLUG.jsonl"
AUDIT="$MEMORY/suppression-log-$SLUG.jsonl"
RISKS="$TARGET/ACCEPTED-RISKS.md"

if [[ ! -f "$FINDINGS" ]]; then
  echo "error: findings file missing: $FINDINGS" >&2
  echo "  (Phase 1 + 1b must run before Phase 1c)" >&2
  exit 3
fi

# ACCEPTED-RISKS.md optional — skip gracefully if absent
python3 "$LIB" \
  --findings "$FINDINGS" \
  --accepted-risks "$RISKS" \
  --suppressed-out "$SUPPRESSED" \
  --audit-log-out "$AUDIT" \
  --skip-if-missing-risks
