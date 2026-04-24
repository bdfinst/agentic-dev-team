#!/usr/bin/env bash
# consumer-stub-fail-open.sh — minimal reference implementation of the
# Gap-6-class consumer that depends on the RECON envelope's file_inventory
# field + sibling file. Used by backward-compat-1.2.0.sh to prove the three
# fail-open branches in the contract doc are live and coherent.
#
# Usage:
#   consumer-stub-fail-open.sh <envelope.json> <memory-dir>
#
# Behavior:
#   branch a (field absent)    -> stderr: "[recon-inventory] notice: file_inventory field absent on envelope; proceeding without membership check"
#   branch b (sibling absent)  -> stderr: "[recon-inventory] notice: sibling file <path> missing; proceeding without membership check"
#   branch c (count mismatch)  -> stderr: "[recon-inventory] notice: file_inventory.count (<declared>) != wc -l <sibling> (<actual>); proceeding without membership check"
#   happy path                 -> stderr silent, exit 0
# Always exits 0 (fail-open).

set -euo pipefail

if [[ $# -ne 2 ]]; then
  printf 'usage: %s <envelope.json> <memory-dir>\n' "$0" >&2
  exit 2
fi
ENVELOPE="$1"
MEMORY_DIR="$2"

if [[ ! -r "$ENVELOPE" ]]; then
  printf '[recon-inventory] error: envelope unreadable at %s\n' "$ENVELOPE" >&2
  exit 0
fi

# Branch a: field absent.
SIBLING_REF="$(python3 -c 'import json,sys
try:
    with open(sys.argv[1]) as f:
        d=json.load(f)
    fi=d.get("file_inventory")
    print(fi["sibling_ref"] if fi else "")
except Exception:
    print("")
' "$ENVELOPE")"

if [[ -z "$SIBLING_REF" ]]; then
  printf '[recon-inventory] notice: file_inventory field absent on envelope; proceeding without membership check\n' >&2
  exit 0
fi

SIBLING_PATH="$MEMORY_DIR/$SIBLING_REF"

# Branch b: sibling file absent.
if [[ ! -r "$SIBLING_PATH" ]]; then
  printf '[recon-inventory] notice: sibling file %s missing; proceeding without membership check\n' "$SIBLING_PATH" >&2
  exit 0
fi

# Branch c: count mismatch.
DECLARED_COUNT="$(python3 -c 'import json,sys
with open(sys.argv[1]) as f:
    print(json.load(f)["file_inventory"]["count"])
' "$ENVELOPE")"
ACTUAL_COUNT=$(wc -l <"$SIBLING_PATH" | tr -d ' ')

if [[ "$DECLARED_COUNT" != "$ACTUAL_COUNT" ]]; then
  printf '[recon-inventory] notice: file_inventory.count (%s) != wc -l %s (%s); proceeding without membership check\n' \
    "$DECLARED_COUNT" "$SIBLING_PATH" "$ACTUAL_COUNT" >&2
  exit 0
fi

# Happy path — no stderr, exit 0.
exit 0
