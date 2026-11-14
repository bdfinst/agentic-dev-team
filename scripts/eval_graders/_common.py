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


# The output key holding an agent's verdict when a spec names no `statusField`.
DEFAULT_STATUS_FIELD = "status"


def check_status(spec: dict, output: dict | None) -> list[str]:
    """The `expectedStatus` check: empty when the spec sets none or the verdict matches.

    `output` is the agent's JSON; None means the answer had no JSON, so a required
    verdict is missing.
    """
    if "expectedStatus" not in spec:
        return []
    field = spec.get("statusField", DEFAULT_STATUS_FIELD)
    expected = spec["expectedStatus"]
    if output is None:
        return [f"{field}: expected {expected!r}, but the answer has no JSON verdict"]
    got = output.get(field)
    if got != expected:
        return [f"{field}: expected {expected!r}, got {got!r}"]
    return []
