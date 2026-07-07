#!/usr/bin/env python3
"""Close an epic issue once every one of its sub-issues is closed (#987).

GitHub's native sub-issues feature tracks completion percentage only — it
does not close a parent/epic issue when every sub-issue closes (verified
directly on epic #971, which stayed OPEN at 100% sub-issue completion until
closed by hand). This script is invoked by
`.github/workflows/epic-auto-close.yml` on every `issues: closed` event; it
inspects the closed issue's parent (if any) and closes the parent once every
sibling sub-issue is closed.

Usage: epic_auto_close.py --repo OWNER/REPO --issue N

Stdlib-only. Python 3.8+.
"""

from __future__ import annotations


def should_close_parent(sub_issues: list) -> bool:
    """Return True only when every sub-issue is closed.

    `state_reason` is never inspected — a "closed" issue is closed regardless
    of whether it was completed or marked not-planned. An empty list returns
    False: there is nothing to confirm complete.
    """
    if not sub_issues:
        return False
    return all(issue.get("state") == "closed" for issue in sub_issues)
