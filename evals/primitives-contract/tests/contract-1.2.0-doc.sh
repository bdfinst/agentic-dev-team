#!/usr/bin/env bash
# Doc-semantic assertions on security-primitives-contract.md for 1.2.0:
#   1. Front-matter `version: 1.2.0`
#   2. Changelog entry `### 1.2.0 (YYYY-MM-DD)` exists
#   3. `file_inventory` appears under the `## Envelope 1 — RECON` heading
#      (not merely anywhere)
#   4. `### Consumer error contract` subsection exists under Envelope 1

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
DOC="$REPO_ROOT/plugins/agentic-dev-team/knowledge/security-primitives-contract.md"

fail=0

# 1. version front-matter
if ! awk '/^---$/{n++} n==1 && /^version:[[:space:]]*1\.2\.0[[:space:]]*$/{found=1} END{exit !found}' "$DOC"; then
  printf '[FAIL] contract doc front-matter does not show version: 1.2.0\n' >&2
  fail=$((fail + 1))
else
  printf '[ok]   front-matter version: 1.2.0\n'
fi

# 2. Changelog entry with a dated 1.2.0 heading.
if ! grep -E '^### 1\.2\.0 \([0-9]{4}-[0-9]{2}-[0-9]{2}\)$' "$DOC" >/dev/null; then
  printf '[FAIL] no ### 1.2.0 (YYYY-MM-DD) Changelog entry\n' >&2
  fail=$((fail + 1))
else
  printf '[ok]   Changelog entry for 1.2.0 present\n'
fi

# 3. file_inventory must appear between `## Envelope 1` and the next `## ` heading.
if ! awk '
  /^## Envelope 1/{in_env=1; next}
  in_env && /^## /{in_env=0}
  in_env && /file_inventory/{found=1}
  END{exit !found}
' "$DOC"; then
  printf '[FAIL] file_inventory not documented under ## Envelope 1\n' >&2
  fail=$((fail + 1))
else
  printf '[ok]   file_inventory documented under Envelope 1\n'
fi

# 4. ### Consumer error contract subsection under Envelope 1.
if ! awk '
  /^## Envelope 1/{in_env=1; next}
  in_env && /^## /{in_env=0}
  in_env && /^### Consumer error contract/{found=1}
  END{exit !found}
' "$DOC"; then
  printf '[FAIL] ### Consumer error contract subsection missing under Envelope 1\n' >&2
  fail=$((fail + 1))
else
  printf '[ok]   ### Consumer error contract subsection present\n'
fi

if [[ $fail -ne 0 ]]; then
  printf '\nFAIL: %d check(s) failed\n' "$fail" >&2
  exit 1
fi
printf '\nOK: contract-1.2.0-doc tests passed\n'
