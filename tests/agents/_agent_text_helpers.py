"""Sentence helpers shared by the agent-text contract tests (#2271).

Agent prose is hard-wrapped, so every helper collapses whitespace before it
splits on sentence-ending punctuation.
"""

from __future__ import annotations

import re

import skill_doc_helpers


def sentences(block: str) -> list[str]:
    """Split `block` into sentences after collapsing all whitespace runs."""
    return re.split(r"(?<=[.!?])\s+", " ".join(block.split()))


def sentence_containing(block: str, needle: str) -> str:
    """Return the one sentence in `block` that contains `needle`."""
    hits = [s for s in sentences(block) if needle in s]
    assert len(hits) == 1, f"expected exactly one sentence with {needle!r}, got {hits}"
    return hits[0]


def has_sentence_with_all(block: str, *needles: str) -> bool:
    """True when a single sentence in `block` contains every needle."""
    return any(all(n in s for n in needles) for s in sentences(block))


def required_section(
    text: str,
    start_pattern: str,
    boundary_pattern: str = r"^## ",
    include_start_line: bool = False,
    name: str | None = None,
) -> str:
    """Extract a section via `skill_doc_helpers.section()` and assert it was
    actually found, raising a clear `AssertionError` (naming `name`, or a
    pattern-derived message when `name` is omitted) rather than letting a
    silently-empty section pass downstream assertions vacuously."""
    result = skill_doc_helpers.section(
        text,
        start_pattern,
        boundary_pattern=boundary_pattern,
        include_start_line=include_start_line,
    )
    label = name if name is not None else f"section matching {start_pattern!r}"
    assert result, f"{label} not found in text"
    return result
