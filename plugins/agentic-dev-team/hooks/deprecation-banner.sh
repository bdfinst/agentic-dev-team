#!/usr/bin/env bash
# plugins/agentic-dev-team/hooks/deprecation-banner.sh
#
# SessionStart hook for the agentic-dev-team DEPRECATION STUB.
#
# Fires on every Claude Code session start. Prints a high-visibility
# notice that the user is on a deprecation stub, names the real plugin,
# and shows the exact /upgrade flow to finish migrating.
#
# Why this hook exists: in the wild we saw users running the pre-rename
# /upgrade twice without restarting in between — the first run installed
# this stub, the second run was still the pre-rename code (not the stub's
# /upgrade) and reported "already at latest." Users walked away thinking
# they were done. This banner makes the half-migrated state impossible
# to miss on the next session start.
#
# Output format: the hook emits a single JSON object on stdout, per the
# Claude Code SessionStart hook contract. The `additionalContext` field
# is shown to the model and the user.

cat <<'EOF'
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "DEPRECATION NOTICE — agentic-dev-team@bfinster is a deprecation stub. The real plugin has been renamed to dev-team@bfinster.\n\nTo finish migrating:\n  1. Run /upgrade (this stub will install dev-team@bfinster and remove itself)\n  2. Restart Claude Code\n\nAfter migration you'll have the full team back: orchestrator, software-engineer, qa-engineer, all reviewers, /code-review, /plan, /build, /pr, and every skill — under the new plugin id.\n\nIf you've already run /upgrade in this session and it reported 'already at latest', that was the pre-rename code running against this stub. Restart Claude Code first, then run /upgrade once more — that second /upgrade is THIS stub's command, and it WILL migrate you."
  }
}
EOF
