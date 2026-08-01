#!/usr/bin/env python3
"""token_efficiency_limits — shared thresholds for token-efficiency checks.

Single source of truth for the limits enforced by both
`hooks/token_efficiency_review.py` (the shipped PostToolUse hook) and
`plugins/dev-team/scripts/token_efficiency_review.py` (the review-agent CI runner). Both
previously hardcoded their own copy of these numbers.

Stdlib-only. See docs/python-hook-contract.md.
"""

from __future__ import annotations

# CLAUDE.md character-count limit (advisory in the hook, hard error in CI).
CLAUDE_MD_CHAR_LIMIT: int = 5000

# Any tracked source/CLAUDE.md file's line-count limit.
FILE_LINE_LIMIT: int = 500

# CLAUDE.md rule-count limit. Lives here rather than as a local literal in the
# CI runner (#1651) so this module's "single source of truth" claim above is
# true of every limit, not just the two that happened to be duplicated when it
# was written. Only the CI runner reads it today — the shipped hook does not
# count rules — but a second reader is exactly how the other two limits drifted
# into needing this module in the first place.
CLAUDE_MD_RULE_LIMIT: int = 200
