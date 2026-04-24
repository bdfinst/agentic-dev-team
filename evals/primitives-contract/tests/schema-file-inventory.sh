#!/usr/bin/env bash
# Tests schema conformance of file_inventory fixtures against recon-envelope-v1 schema.
#
# Positive: recon-envelope-with-file-inventory.json — must validate.
# Negative: recon-envelope-file-inventory-malformed-source.json — must NOT validate
#           (source enum violation).
# Negative: recon-envelope-file-inventory-partial.json — must NOT validate
#           (missing count + sibling_ref in sub-object).
# Contract-freeze: file-inventory-consumer-contract.json — AC-12 shape check.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
SCHEMA="$REPO_ROOT/plugins/agentic-dev-team/knowledge/schemas/recon-envelope-v1.json"
FIXTURE_DIR="$REPO_ROOT/evals/primitives-contract/fixtures"
VALIDATE="$REPO_ROOT/evals/primitives-contract/validate.sh"

fail=0

# Positive
if "$VALIDATE" "$SCHEMA" "$FIXTURE_DIR/recon-envelope-with-file-inventory.json" >/dev/null 2>&1; then
  printf '[ok]   positive: recon-envelope-with-file-inventory.json\n'
else
  printf '[FAIL] positive: recon-envelope-with-file-inventory.json did NOT validate\n' >&2
  fail=$((fail + 1))
fi

# Negative — bad source enum
if "$VALIDATE" "$SCHEMA" "$FIXTURE_DIR/recon-envelope-file-inventory-malformed-source.json" >/dev/null 2>&1; then
  printf '[FAIL] negative: malformed-source was accepted (should have failed)\n' >&2
  fail=$((fail + 1))
else
  printf '[ok]   negative: malformed-source rejected\n'
fi

# Negative — partial sub-object
if "$VALIDATE" "$SCHEMA" "$FIXTURE_DIR/recon-envelope-file-inventory-partial.json" >/dev/null 2>&1; then
  printf '[FAIL] negative: partial sub-object was accepted (should have failed)\n' >&2
  fail=$((fail + 1))
else
  printf '[ok]   negative: partial sub-object rejected\n'
fi

# Contract-freeze fixture (AC-12): assert its shape
python3 - "$FIXTURE_DIR/file-inventory-consumer-contract.json" <<'PY' || fail=$((fail + 1))
import json, sys
with open(sys.argv[1]) as f:
    doc = json.load(f)
expected = {"source", "count", "sibling_ref"}
required = set(doc.get("required_properties", []))
if required != expected:
    print(f"[FAIL] consumer-contract required_properties {required} != {expected}", file=sys.stderr)
    sys.exit(1)
types = doc.get("property_types", {})
if types.get("source") != "string" or types.get("count") != "integer" or types.get("sibling_ref") != "string":
    print(f"[FAIL] consumer-contract property_types wrong: {types}", file=sys.stderr)
    sys.exit(1)
print("[ok]   consumer-contract shape frozen")
PY

if [[ $fail -ne 0 ]]; then
  printf '\nFAIL: %d check(s) failed\n' "$fail" >&2
  exit 1
fi
printf '\nOK: schema-file-inventory tests passed\n'
