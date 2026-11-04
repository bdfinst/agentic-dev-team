"""plan_record_parse — read the facts a feature record needs from plan Markdown.

Sibling of `plan_parse.py`, which owns slice and fence handling. Every parser
here takes plain text and returns plain data; none reads a file or raises on
odd input. Fence awareness comes from `plan_parse.iter_slice_body_lines`, so
there is one fence walker.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterator
from pathlib import Path

_LIB = str(Path(__file__).resolve().parent)
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

import plan_parse

_H1_H2_RE = re.compile(r"^#{1,2}\s")
_CRITERION_ITEM_RE = re.compile(r"^(?:[-*]|\d+[.)])\s+(?:\[[ xX]\]\s+)?(.*)$")
_CRITERION_ID_RE = re.compile(r"^(AC\d+)\b[:.]?\s*(.*)$")
_STEP_HEADING_RE = re.compile(r"^####\s+Step\s+(\d+(?:\.\d+)*)")
_COVERS_RE = re.compile(r"^\**Covers\**\s*:\s*\**\s*(.*)$")
_COVERS_TOKEN_RE = re.compile(r"^(AC\d+)\b")


def _section_lines(text: str, heading: str) -> Iterator[str]:
    """Yield the non-fenced lines under the exact `heading` line, up to the
    next H1 or H2. Heading-like lines inside a fence neither start nor end a
    section. A repeated heading re-opens the section."""
    inside = False
    for line, in_fence in plan_parse.iter_slice_body_lines(text):
        if in_fence:
            continue
        if line.strip() == heading:
            inside = True
        elif _H1_H2_RE.match(line):
            inside = False
        elif inside:
            yield line


def parse_criteria(text: str) -> list[dict[str, str]]:
    """Return `[{"id", "text"}]` for the items under `## Acceptance Criteria`.

    The id is the explicit leading `AC<n>` token when present, else the item's
    1-based position. A repeated explicit id keeps its text; the later
    duplicate takes its position id. Only unindented list items count, so a
    nested sub-bullet is not a criterion.
    """
    criteria: list[dict[str, str]] = []
    seen: set[str] = set()
    for line in _section_lines(text, "## Acceptance Criteria"):
        item = _CRITERION_ITEM_RE.match(line.rstrip())
        if not item:
            continue
        position = f"AC{len(criteria) + 1}"
        body = item.group(1).strip()
        explicit = _CRITERION_ID_RE.match(body)
        if explicit and explicit.group(1) not in seen:
            cid, body = explicit.group(1), explicit.group(2).strip()
        elif explicit:
            cid, body = position, explicit.group(2).strip()
        else:
            cid = position
        seen.add(cid)
        criteria.append({"id": cid, "text": body})
    return criteria


def parse_covers(text: str) -> dict[str, list[str]]:
    """Return `{step_id: [criterion ids]}` from `**Covers**: AC2, AC7` lines.

    A Covers line belongs to the nearest preceding `#### Step N.M` heading.
    Lines inside fenced blocks are ignored, as are Covers lines before any
    step heading and lines that name no `AC<n>` id (template placeholders).
    Several Covers lines in one step merge, keeping first-seen order.
    """
    covers: dict[str, list[str]] = {}
    step: str | None = None
    for line, in_fence in plan_parse.iter_slice_body_lines(text):
        if in_fence:
            continue
        heading = _STEP_HEADING_RE.match(line)
        if heading:
            step = heading.group(1)
            continue
        if step is None:
            continue
        covers_line = _COVERS_RE.match(line.strip())
        if not covers_line:
            continue
        ids = [
            token.group(1)
            for part in covers_line.group(1).split(",")
            if (token := _COVERS_TOKEN_RE.match(part.strip()))
        ]
        if ids:
            merged = covers.setdefault(step, [])
            merged.extend(i for i in dict.fromkeys(ids) if i not in merged)
    return covers
