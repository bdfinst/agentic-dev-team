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
from commit_evidence import STEP_PATTERN

_H1_H2_RE = re.compile(r"^#{1,2}\s")
_CRITERION_ITEM_RE = re.compile(r"^(?:[-*]|\d+[.)])\s+(?:\[[ xX]\]\s+)?(.*)$")
_CRITERION_ID_RE = re.compile(r"^(AC\d+)\b[:.]?\s*(.*)$")
_STEP_HEADING_RE = re.compile(r"^####\s+Step\s+(\d+(?:\.\d+)*)")
_STEP_ENDING_HEADING_RE = re.compile(r"^#{1,3}\s")
_COVERS_RE = re.compile(r"^\**Covers\**\s*:\s*\**\s*(.*)$")
_COVERS_TOKEN_RE = re.compile(r"^(AC\d+)\b")
_SCENARIO_RE = re.compile(r"^(?:Scenario Outline|Scenario):\s*(.*)$")
_DOC_STRING_FENCE = '"""'
# The Build Progress item line is `commit_evidence.STEP_PATTERN`, the one
# definition the progress guardian and the commit evidence rule also use, so
# the record's items are exactly the lines they parse.
_PROGRESS_ITEM_RE = STEP_PATTERN
_PROGRESS_STEP_PREFIX_RE = re.compile(r"^-\s+\[[ xX]\]\s+Step\s+([\d.]+):")
# One grammar for both blocker lines: `**Open blocker**: Slice 2 - text` and
# `**Resolved blocker**: Slice 2 - text`, optionally behind a list marker, with
# the colon outside or inside the bold (`**Open blocker:**`). The caller
# strips the line, so the tail needs no trailing-space handling (a lazy tail
# with `\s*$` backtracks quadratically on a long run of spaces).
_BLOCKER_RE = re.compile(
    r"^(?:[-*]\s+)?\*\*(Open|Resolved) blocker(?:\*\*\s*:|:\*\*)\s*Slice\s+(\d+)\s+-\s+(.+)$"
)
_PROGRESS_SLICE_RE = re.compile(r"^[Ss]lice\s+(\d[^:\s]*)")


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

    The first item carrying an explicit `AC<n>` token owns that id, wherever
    it sits, so a prefixed id never moves. Every other item (unprefixed, or a
    repeat of an id already owned) takes the lowest unused `AC<k>` counting up
    from its 1-based position, so ids are always unique. Only unindented list
    items count, so a nested sub-bullet is not a criterion.
    """
    parsed: list[tuple[str | None, str]] = []
    for line in _section_lines(text, "## Acceptance Criteria"):
        item = _CRITERION_ITEM_RE.match(line.rstrip())
        if not item:
            continue
        body = item.group(1).strip()
        explicit = _CRITERION_ID_RE.match(body)
        parsed.append(
            (explicit.group(1), explicit.group(2).strip()) if explicit else (None, body)
        )

    owners: dict[str, int] = {}
    for index, (explicit_id, _body) in enumerate(parsed):
        if explicit_id is not None:
            owners.setdefault(explicit_id, index)
    taken = set(owners)

    criteria: list[dict[str, str]] = []
    for index, (explicit_id, body) in enumerate(parsed):
        if explicit_id is not None and owners[explicit_id] == index:
            cid = explicit_id
        else:
            number = index + 1
            while f"AC{number}" in taken:
                number += 1
            cid = f"AC{number}"
            taken.add(cid)
        criteria.append({"id": cid, "text": body})
    return criteria


def parse_covers(text: str) -> dict[str, list[str]]:
    """Return `{step_id: [criterion ids]}` from `**Covers**: AC2, AC7` lines.

    A Covers line belongs to the nearest preceding `#### Step N.M` heading;
    any later H1-H3 heading ends that step.
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
        if _STEP_ENDING_HEADING_RE.match(line):
            step = None
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


def parse_scenarios(slice_text: str) -> list[str]:
    """Return the titles of the `Scenario:` and `Scenario Outline:` lines in
    the slice's first gherkin fence, in order.

    `slice_text` is one slice section; its `### Slice` heading is optional.
    A `Scenario:` line inside a triple-quote doc string, or in any fence after the
    first gherkin one, is not a scenario.
    """
    blocks = plan_parse.slice_gherkin_blocks(
        ["### Slice 0: _", *slice_text.splitlines()]
    )
    gherkin = next((g for _id, _title, g in blocks if g is not None), "")
    titles: list[str] = []
    in_doc_string = False
    for line in gherkin.splitlines():
        stripped = line.strip()
        if stripped.count(_DOC_STRING_FENCE) % 2:
            in_doc_string = not in_doc_string
            continue
        if in_doc_string:
            continue
        scenario = _SCENARIO_RE.match(stripped)
        if scenario:
            titles.append(scenario.group(1).strip())
    return titles


def parse_step_ids(slice_text: str) -> list[str]:
    """Return the `N.M` ids of the `#### Step N.M` headings, fence-aware."""
    ids = []
    for line, in_fence in plan_parse.iter_slice_body_lines(slice_text):
        heading = None if in_fence else _STEP_HEADING_RE.match(line)
        if heading:
            ids.append(heading.group(1))
    return ids


def parse_build_progress(text: str) -> dict[str, object]:
    """Return `{"legacy": bool, "items": [{kind, id, header, done}]}`.

    Reads exactly what `progress_guardian.parse_plan` reads: unindented
    `- [ ]` / `- [x]` lines inside `## Build Progress` (up to the next `## `
    heading), skipping the `### Acceptance Criteria` mirror. A plan with no
    `## Build Progress` heading is `legacy`: every line of the file is
    scanned. Not fence-aware, on purpose: the guardian is not.

    A line with a `Step N.M:` prefix is a `step` with id `N.M`, whatever its
    title says. Otherwise `kind` is `slice` when the header starts `Slice <n>`
    (id `<n>`), else `step` with the header itself as id.
    """
    lines = text.splitlines()
    legacy = not any(line.rstrip().startswith("## Build Progress") for line in lines)
    items: list[dict[str, object]] = []
    in_section = legacy
    in_mirror = False
    for raw in lines:
        line = raw.rstrip()
        if not legacy:
            if line.startswith("## Build Progress"):
                in_section, in_mirror = True, False
                continue
            if in_section and line.startswith("## "):
                in_section = False
                continue
            if in_section and line.startswith("### Acceptance Criteria"):
                in_mirror = True
                continue
            if in_mirror and line.startswith("### "):
                in_mirror = False
        if not in_section or in_mirror:
            continue
        item = _PROGRESS_ITEM_RE.match(line)
        if item:
            items.append(_progress_item(line, item.group(1), item.group(2).strip()))
    return {"legacy": legacy, "items": items}


def _progress_item(line: str, flag: str, header: str) -> dict[str, object]:
    step_match = _PROGRESS_STEP_PREFIX_RE.match(line)
    slice_match = None if step_match else _PROGRESS_SLICE_RE.match(header)
    if step_match:
        kind, item_id = "step", step_match.group(1)
    elif slice_match:
        kind, item_id = "slice", slice_match.group(1)
    else:
        kind, item_id = "step", header
    return {"kind": kind, "id": item_id, "header": header, "done": flag.lower() == "x"}


def parse_blockers(text: str) -> dict[str, list[dict[str, str]]]:
    """Return `{"open": [...], "resolved": [...]}` of `{"slice", "text"}` from
    the blocker lines under `## Plan Review Summary`.

    Reads the lines only; a resolved blocker does not cancel an open one here
    (the check does that). Lines outside the section, or inside a fence, are
    ignored.
    """
    blockers: dict[str, list[dict[str, str]]] = {"open": [], "resolved": []}
    for line in _section_lines(text, "## Plan Review Summary"):
        match = _BLOCKER_RE.match(line.strip())
        if match:
            blockers[match.group(1).lower()].append(
                {"slice": match.group(2), "text": match.group(3)}
            )
    return blockers
