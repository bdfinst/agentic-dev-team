#!/usr/bin/env bash
# plugins/agentic-security-assessment/hooks/deprecation-banner.sh
#
# SessionStart hook for the agentic-security-assessment DEPRECATION STUB.
# Mirrors plugins/agentic-dev-team/hooks/deprecation-banner.sh; see that
# file for the rationale and design notes.

cat <<'EOF'
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "DEPRECATION NOTICE — agentic-security-assessment@bfinster is a deprecation stub. The real plugin has been renamed to security-assessment@bfinster.\n\nTo finish migrating:\n  1. Run /upgrade (this stub will install security-assessment@bfinster and remove itself)\n  2. Restart Claude Code\n\nAfter migration you'll have the full security companion back: /security-assessment, /cross-repo-analysis, /redteam-model, /export-pdf, the SARIF-first pipeline, and every FP-reduction / compliance-mapping skill — under the new plugin id.\n\nIf you've already run /upgrade in this session and it reported 'already at latest', that was the pre-rename code running against this stub. Restart Claude Code first, then run /upgrade once more — that second /upgrade is THIS stub's command, and it WILL migrate you."
  }
}
EOF
