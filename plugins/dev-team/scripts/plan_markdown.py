"""plan_markdown.py — line-level helpers for editing a plan's markdown.

Splits text into lines that keep their endings, finds ATX headings and the
sections they open (ignoring fenced code), and splices replacement lines in
without disturbing the bytes around them. `plan_summary_record.py` is the
caller; nothing here knows about candidates or tables.

Errors are ValueError with a message the caller prints.

Stdlib only (ADR 0014, ADR 0015, ADR 0031).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_FENCE_RE = re.compile(r"\s*(`{3,}|~{3,})(.*)")
_HEADING_RE = re.compile(r"(#{1,6}) +(.*?) *")
_LINE_RE = re.compile(r"[^\n]*\n|[^\n]+")


@dataclass(frozen=True)
class Heading:
    index: int
    level: int
    title: str


@dataclass(frozen=True)
class Section:
    """Lines `start` (the heading) up to but excluding `end`."""

    start: int
    end: int


def split_lines(text: str) -> list[str]:
    """Lines with their line ending kept; unlike str.splitlines, only "\\n"
    splits."""
    return _LINE_RE.findall(text)


def line_ending(lines: list[str]) -> str:
    """The plan's line ending, taken from its first line: "\\r\\n" when that
    line ends in it, else "\\n"."""
    return "\r\n" if lines and lines[0].endswith("\r\n") else "\n"


def fence_after(open_fence: str | None, text: str) -> str | None:
    """The fence marker still open after `text`, given `open_fence` before.

    A backtick fence's info string may not contain a backtick, so a line like
    "```x```" is inline code, not an opener. This grammar (``` and ~~~, up to
    any indent, closed by a marker at least as long) is deliberately stricter
    than `lib/plan_parse._FenceState` (backtick-only, column 0); the two are
    not shared on purpose.
    """
    fence = _FENCE_RE.fullmatch(text)
    if fence is None:
        return open_fence
    marker, info = fence.groups()
    if open_fence is None:
        is_inline_code = marker[0] == "`" and "`" in info
        return None if is_inline_code else marker
    closes = (
        marker[0] == open_fence[0]
        and len(marker) >= len(open_fence)
        and not info.strip()
    )
    return None if closes else open_fence


def find_headings(lines: list[str]) -> list[Heading]:
    """Every ATX heading at column 0 with a space after the hashes, outside a
    fence; a `# ` heading ends a `## ` section too. A fence that is never
    closed would hide every later heading (CommonMark runs it to the end of
    the file), and a summary appended inside it would be invisible to the
    next run, which would append another: such a plan is rejected."""
    found = []
    open_fence = None
    for index, line in enumerate(lines):
        text = line.rstrip("\r\n")
        was_open = open_fence is not None
        open_fence = fence_after(open_fence, text)
        if was_open or open_fence is not None:
            continue
        heading = _HEADING_RE.fullmatch(text)
        if heading:
            found.append(Heading(index, len(heading.group(1)), heading.group(2)))
    if open_fence is not None:
        raise ValueError("plan has a code fence that is never closed")
    return found


def find_section(
    headings: list[Heading],
    line_count: int,
    level: int,
    title: str,
    within: Section | None = None,
) -> Section | None:
    """The first `level` heading titled `title` (inside `within` when given)
    and the lines up to the next heading of the same or a higher level."""
    first, last = (within.start + 1, within.end) if within else (0, line_count)
    for position, heading in enumerate(headings):
        if first <= heading.index < last and (heading.level, heading.title) == (
            level,
            title,
        ):
            end = next(
                (h.index for h in headings[position + 1 :] if h.level <= level),
                line_count,
            )
            return Section(heading.index, end)
    return None


def content_end(lines: list[str], section: Section) -> int:
    """Index just after the section's last non-blank line."""
    end = section.end
    while end > section.start + 1 and not lines[end - 1].strip():
        end -= 1
    return end


def splice(lines: list[str], start: int, end: int, new: list[str], eol: str) -> str:
    """`lines` with `lines[start:end]` replaced by `new`. A line left without
    its line ending gets `eol`; when only blank lines follow, they are dropped
    so the file ends with exactly one line ending."""
    head = lines[:start]
    if head and not head[-1].endswith("\n"):
        head[-1] += eol
    tail = lines[end:]
    if not any(line.strip() for line in tail):
        tail = []
    return "".join(head + new + tail)


def blank_line_before(lines: list[str], index: int, eol: str) -> list[str]:
    """A blank line to put between `lines[index - 1]` and a block inserted at
    `index`, unless one is already there."""
    return [eol] if index > 0 and lines[index - 1].strip() else []
