#!/usr/bin/env bash
# Asserts the codebase-recon rubric declares inventory-determinism and
# sibling-file-contract-compliance criteria by heading.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
RUBRIC="$REPO_ROOT/evals/codebase-recon/rubric.md"

fail=0

if ! grep -E '^### Inventory determinism' "$RUBRIC" >/dev/null; then
  printf '[FAIL] rubric.md missing ### Inventory determinism heading\n' >&2
  fail=$((fail + 1))
else
  printf '[ok]   rubric has Inventory determinism criterion\n'
fi

if ! grep -E '^### Sibling-file contract compliance' "$RUBRIC" >/dev/null; then
  printf '[FAIL] rubric.md missing ### Sibling-file contract compliance heading\n' >&2
  fail=$((fail + 1))
else
  printf '[ok]   rubric has Sibling-file contract compliance criterion\n'
fi

if [[ $fail -ne 0 ]]; then
  printf '\nFAIL: %d check(s) failed\n' "$fail" >&2
  exit 1
fi
printf '\nOK: rubric-inventory tests passed\n'
