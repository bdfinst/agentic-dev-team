"""Utilities for maintaining a sorted list of scores."""

import bisect


def record_score(scores, value):
    """Insert ``value`` into the sorted list ``scores``, keeping it sorted.

    Uses ``bisect.insort``, which runs in O(log n) — the sorted-list
    invariant lets it avoid a linear rescan on every insert.
    """
    bisect.insort(scores, value)
    return scores
