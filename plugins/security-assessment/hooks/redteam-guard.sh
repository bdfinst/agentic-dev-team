#!/usr/bin/env bash
# redteam-guard.sh — PreToolUse hook for Bash.
#
# Blocks direct invocation of the red-team harness orchestrator unless the
# environment variable REDTEAM_AUTHORIZED=1 is set. The /redteam-model command
# is the canonical entry point — it sets REDTEAM_AUTHORIZED=1 after running
# the scope + consent checks.
#
# Matches all common invocation forms:
#   python orchestrator.py
#   python -m redteam.orchestrator
#   /path/to/orchestrator.py
#   python3 path/to/orchestrator.py
#
# Input:  JSON on stdin with tool_input.command
# Output: exit 2 to block, exit 0 to allow, message on stderr
set -uo pipefail

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)

# If no command (non-Bash tool call), pass through
[ -z "$COMMAND" ] && exit 0

# Match orchestrator invocation forms
if echo "$COMMAND" | grep -qE '(^|[[:space:]/])(python[0-9]*[[:space:]]+(-m[[:space:]]+)?([a-zA-Z0-9_./-]*[[:space:]]+)?(redteam[./]orchestrator|orchestrator\.py)|\.?/?[a-zA-Z0-9_/.-]*orchestrator\.py)'; then
  if [ "${REDTEAM_AUTHORIZED:-}" != "1" ]; then
    cat >&2 <<'EOF'
redteam-guard: blocked direct invocation of the red-team orchestrator.

The harness must be dispatched via /redteam-model, which runs:
  1. Scope check (target resolves to a self-owned CIDR) OR
  2. Self-certification (--self-certify-owned <path>, SHA-256 logged)
  3. Rate limit + query budget validation
before setting REDTEAM_AUTHORIZED=1 in the child env.

To bypass intentionally (e.g. for harness development):
  REDTEAM_AUTHORIZED=1 python -m redteam.orchestrator --dry-run
Any such override must land alongside a documented reason — audit
log records every bypass.
EOF
    exit 2
  fi
fi

exit 0
