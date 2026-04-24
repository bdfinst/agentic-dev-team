#!/usr/bin/env bash
# Asserts the codebase-recon agent prompt documents Step 6.5 (inventory)
# and invokes the canonical script by path; handoff contract mentions
# file_inventory.sibling_ref.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
AGENT="$REPO_ROOT/plugins/agentic-dev-team/agents/codebase-recon.md"

fail=0

# Step 6.5 heading exists.
if ! grep -E '^### 6\.5[[:space:]]' "$AGENT" >/dev/null; then
  printf '[FAIL] codebase-recon.md has no ### 6.5 heading\n' >&2
  fail=$((fail + 1))
else
  printf '[ok]   Step 6.5 heading present\n'
fi

# References the canonical script by path.
if ! grep -F 'scripts/recon-inventory.sh' "$AGENT" >/dev/null; then
  printf '[FAIL] codebase-recon.md does not reference scripts/recon-inventory.sh\n' >&2
  fail=$((fail + 1))
else
  printf '[ok]   canonical script path referenced\n'
fi

# Handoff contract mentions file_inventory.sibling_ref.
if ! awk '
  /^## Handoff contract/{in_ho=1; next}
  in_ho && /^## /{in_ho=0}
  in_ho && /file_inventory\.sibling_ref/{found=1}
  END{exit !found}
' "$AGENT"; then
  printf '[FAIL] Handoff contract does not mention file_inventory.sibling_ref\n' >&2
  fail=$((fail + 1))
else
  printf '[ok]   handoff contract mentions file_inventory.sibling_ref\n'
fi

if [[ $fail -ne 0 ]]; then
  printf '\nFAIL: %d check(s) failed\n' "$fail" >&2
  exit 1
fi
printf '\nOK: agent-has-step-6-5 tests passed\n'
