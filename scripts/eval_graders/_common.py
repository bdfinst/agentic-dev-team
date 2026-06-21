"""Shared helpers for grader modules (issue #309).

These were inline in scripts/eval_grade.py before the registry split. They are
deliberately tiny and dependency-free so every grader can rely on them.
"""

from __future__ import annotations


def in_range(n: int, rng: dict) -> bool:
    """True when n is within the inclusive {min,max} range (open-ended max)."""
    lo = rng.get("min", 0)
    hi = rng.get("max", float("inf"))
    return lo <= n <= hi


def mentions(haystack: str, needle: str) -> bool:
    """Case-insensitive substring membership (the keyword-check primitive)."""
    return needle.lower() in haystack.lower()
