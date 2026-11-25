"""detect_bullets — shared parser for the check bullets in an agent's ``## Detect`` section.

One definition of "a Detect bullet" for every consumer (tag checker, audit,
tests), so none of them re-implements the markdown walk and drifts.

A Detect bullet is a top-level ``- `` item between the ``## Detect`` heading
and the next level-2 heading. Indented lines that follow it, including nested
bullets, belong to it. An unindented line (blank, a new bullet, a bare
paragraph) ends it, so a bullet's trailing tag is never absorbed into the
next, unrelated paragraph. Tags are ``[MECHANICAL]`` and ``[JUDGMENT]``,
case-exact.
"""

from __future__ import annotations

import re
from typing import NamedTuple

TAG_PATTERN = re.compile(r"\[(MECHANICAL|JUDGMENT)\]")
BULLET_START = re.compile(r"^- ")
CONTINUATION = re.compile(r"^[ \t]+\S")
_DETECT_HEADING = "## Detect"
# Level-2 only: ``###`` subheadings stay inside the Detect section.
_NEXT_H2 = re.compile(r"^##(?!#)")


class DetectBullet(NamedTuple):
    line: int  # 1-based line of the bullet's first line in the source text
    text: str  # the bullet with its continuation lines, newline-joined
    tags: list[str]


def tags(block: str) -> list[str]:
    """Return every ``[MECHANICAL]``/``[JUDGMENT]`` tag in ``block``, in order."""
    return TAG_PATTERN.findall(block)


def section_between(text: str, start_heading: str, end_heading: str) -> str:
    """Return the text after ``start_heading`` up to the next ``end_heading``.

    Raises ``ValueError`` when either marker is absent.
    """
    start = text.index(start_heading) + len(start_heading)
    end = text.index(end_heading, start)
    return text[start:end]


def _bullet_spans(lines: list[str]) -> list[tuple[int, int]]:
    """Return ``(start, end)`` index pairs, end exclusive, one per top-level bullet."""
    spans: list[tuple[int, int]] = []
    i, n = 0, len(lines)
    while i < n:
        if BULLET_START.match(lines[i]):
            j = i + 1
            while j < n and CONTINUATION.match(lines[j]):
                j += 1
            spans.append((i, j))
            i = j
        else:
            i += 1
    return spans


def bullet_blocks(section: str) -> list[str]:
    """Split ``section`` into top-level bullets, each with its continuation lines."""
    lines = section.split("\n")
    return ["\n".join(lines[start:end]) for start, end in _bullet_spans(lines)]


def detect_bullets(text: str) -> list[DetectBullet]:
    """Return the bullets under ``## Detect``, or ``[]`` when there is no such section."""
    lines = text.split("\n")
    try:
        heading_index = lines.index(_DETECT_HEADING)
    except ValueError:
        return []
    body_start = heading_index + 1
    body_end = next(
        (i for i in range(body_start, len(lines)) if _NEXT_H2.match(lines[i])),
        len(lines),
    )
    body = lines[body_start:body_end]
    found: list[DetectBullet] = []
    for start, end in _bullet_spans(body):
        block = "\n".join(body[start:end])
        found.append(DetectBullet(body_start + start + 1, block, tags(block)))
    return found
