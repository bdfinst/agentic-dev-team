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
