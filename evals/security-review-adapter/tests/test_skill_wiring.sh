#!/usr/bin/env bash
# Static-analysis-integration SKILL.md Tier 3 references the adapter's new path,
# and the companion security-assessment-pipeline SKILL.md Phase 1b block references
# the full adapter path. AC-14.
set -u
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
SKILL="$REPO_ROOT/plugins/agentic-dev-team/skills/static-analysis-integration/SKILL.md"
PIPELINE="$REPO_ROOT/plugins/agentic-security-assessment/skills/security-assessment-pipeline/SKILL.md"

rc=0
if ! grep -qF "adapters/security-review-adapter.py" "$SKILL"; then
  echo "FAIL: static-analysis-integration/SKILL.md missing Tier 3 adapter reference" >&2
  rc=1
fi
if ! grep -qF "plugins/agentic-dev-team/skills/static-analysis-integration/adapters/security-review-adapter.py" "$PIPELINE"; then
  echo "FAIL: security-assessment-pipeline/SKILL.md Phase 1b missing full adapter path reference" >&2
  rc=1
fi
[[ $rc -eq 0 ]] && echo "OK skill wiring"
exit $rc
