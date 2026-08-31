#!/usr/bin/env python3
"""token_efficiency_limits — shared thresholds for token-efficiency checks.

Single source of truth for the limits enforced by both
`hooks/token_efficiency_review.py` (the shipped PostToolUse hook) and
`plugins/dev-team/scripts/token_efficiency_review.py` (the review-agent CI runner). Both
previously hardcoded their own copy of these numbers.

It is also the single source of truth for two small pieces of *logic* that
drifted between those same two callers: which filename counts as "CLAUDE.md"
and how "character count" is measured. The hook used to match only the exact
case `CLAUDE.md` and count bytes; the CI runner matched case-insensitively
and counted decoded characters — so the same file could report two different
counts, or be checked in one caller and silently skipped in the other,
depending on nothing but its name's casing.

Stdlib-only. See docs/python-hook-contract.md.
"""

from __future__ import annotations

from pathlib import Path

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


def is_claude_md_file(path: Path) -> bool:
    """Return True when `path`'s filename is CLAUDE.md, case-insensitively."""
    return path.name.lower() == "claude.md"


def char_count(path: Path) -> int:
    """Return the decoded character count of `path`.

    Character count, not byte count: `CLAUDE_MD_CHAR_LIMIT` is a token-budget
    proxy, and decoded characters track token count far more closely than
    bytes do for any file containing multi-byte UTF-8 sequences.
    """
    return len(path.read_text(encoding="utf-8", errors="replace"))
