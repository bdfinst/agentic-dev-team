"""Sentence helpers shared by the agent-text contract tests (#2271).

Agent prose is hard-wrapped, so every helper collapses whitespace before it
splits on sentence-ending punctuation.
"""

from __future__ import annotations

import re


def sentences(block: str) -> list[str]:
    """Split `block` into sentences after collapsing all whitespace runs."""
    return re.split(r"(?<=[.!?])\s+", " ".join(block.split()))


def sentence_containing(block: str, needle: str) -> str:
    """Return the one sentence in `block` that contains `needle`."""
    hits = [s for s in sentences(block) if needle in s]
    assert len(hits) == 1, f"expected exactly one sentence with {needle!r}, got {hits}"
    return hits[0]


def sentence_with_all(block: str, *needles: str) -> bool:
    """True when a single sentence in `block` contains every needle."""
    return any(all(n in s for n in needles) for s in sentences(block))
