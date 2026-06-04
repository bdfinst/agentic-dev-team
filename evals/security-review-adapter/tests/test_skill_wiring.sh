#!/usr/bin/env bash
# Static-analysis-integration SKILL.md Tier 3 references the adapter's new path.
# The companion security-assessment-pipeline delegates Phase 1b adapter wiring to
# knowledge/phase-1b-adapters.md, which carries the full adapter path. AC-14.
set -u
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
SKILL="$REPO_ROOT/plugins/dev-team/skills/static-analysis-integration/SKILL.md"
PIPELINE="$REPO_ROOT/plugins/security-assessment/skills/security-assessment-pipeline/SKILL.md"
ADAPTERS_DOC="$REPO_ROOT/plugins/security-assessment/knowledge/phase-1b-adapters.md"

rc=0
if ! grep -qF "adapters/security-review-adapter.py" "$SKILL"; then
  echo "FAIL: static-analysis-integration/SKILL.md missing Tier 3 adapter reference" >&2
  rc=1
fi
if ! grep -qF "phase-1b-adapters.md" "$PIPELINE"; then
  echo "FAIL: security-assessment-pipeline/SKILL.md Phase 1b missing delegation to knowledge/phase-1b-adapters.md" >&2
  rc=1
fi
if ! grep -qF "plugins/dev-team/skills/static-analysis-integration/adapters/security-review-adapter.py" "$ADAPTERS_DOC"; then
  echo "FAIL: phase-1b-adapters.md missing full adapter path reference" >&2
  rc=1
fi
[[ $rc -eq 0 ]] && echo "OK skill wiring"
exit $rc
