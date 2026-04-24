#!/usr/bin/env bash
# Thin wrapper around a JSON Schema (Draft 2020-12) validator.
#
# Usage:
#   validate.sh <schema-path> <instance-path>
#
# Exits 0 if instance validates; non-zero with diagnostic on stderr otherwise.
#
# Implementation: uses Python's jsonschema library (already a dependency of
# evals/primitives-contract/validate.py).

set -euo pipefail

if [[ $# -ne 2 ]]; then
  printf 'usage: %s <schema.json> <instance.json>\n' "$0" >&2
  exit 2
fi

SCHEMA_PATH="$1"
INSTANCE_PATH="$2"

if [[ ! -r "$SCHEMA_PATH" ]]; then
  printf 'validate.sh: cannot read schema at %s\n' "$SCHEMA_PATH" >&2
  exit 2
fi
if [[ ! -r "$INSTANCE_PATH" ]]; then
  printf 'validate.sh: cannot read instance at %s\n' "$INSTANCE_PATH" >&2
  exit 2
fi

python3 - "$SCHEMA_PATH" "$INSTANCE_PATH" <<'PY'
import json
import sys
from jsonschema import Draft202012Validator

schema_path, instance_path = sys.argv[1], sys.argv[2]
with open(schema_path) as f:
    schema = json.load(f)
with open(instance_path) as f:
    instance = json.load(f)

validator = Draft202012Validator(schema)
errors = list(validator.iter_errors(instance))
if errors:
    for e in errors[:10]:
        path = ".".join(str(p) for p in e.absolute_path)
        sys.stderr.write(f"[invalid] @ {path or '<root>'}: {e.message}\n")
    sys.exit(1)
sys.exit(0)
PY
