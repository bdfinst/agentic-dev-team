#!/usr/bin/env bash
# issue-deps.sh — per-slice sibling dependency sets for issue linking, derived
# from the plan's DAG (via plan-waves.sh), NOT from plan file order. Read-only:
# it never edits the plan or plan-waves output.
#
# Emits JSON mapping each slice id to its DIRECT predecessor slice ids:
#   { "A": [], "B": ["A"], "C": ["A"], "D": ["B","C"] }
#
# /issues-from-plan maps those slice ids to the child issue numbers it creates
# and renders "depends on #N" links between siblings.
#
# Usage: issue-deps.sh <plan.md>

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

FILE="${1:-}"
{ [ -n "$FILE" ] && [ -f "$FILE" ]; } || { echo "usage: issue-deps.sh <plan.md>" >&2; exit 2; }

# plan-waves.sh validates the DAG (cycle/missing/unknown -> non-zero); propagate.
"$HERE/plan-waves.sh" "$FILE" | jq '.slices | map_values(.depends_on)'
