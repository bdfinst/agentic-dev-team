"""Examination inputs for the acceptance examiner (#2270).

Pure, stdlib only, no I/O. The code here is the single source of criteria
numbering (`criteria_ids`: `AC1..ACn` by position in `plan_examination_inputs`),
of the checkbox grammar (`CHECKBOX_PREFIX`) and of fenced-block detection
(`scan_fences`), which every other reader of a plan's markdown builds on.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import NamedTuple

AC_SECTION = "Acceptance Criteria"
SLICES_SECTION = "Slices"
GATE_SECTION = "Pre-PR Quality Gate"
EXAMINATION_SECTION = "Acceptance Examination"
GHERKIN_FENCE = "gherkin"
SKILL_COMMAND_PREFIX = "/"
PLAN_MARKER_PREFIX = "Acceptance-examination plan: "

CRITERION_ID_PREFIX = "AC"
CRITERION_ID = re.compile(rf"{CRITERION_ID_PREFIX}\d+", re.ASCII)
#: The start of a plan checkbox line; `progress_guardian.STEP_PATTERN` builds on
#: it. Group `state` is the box content.
CHECKBOX_PREFIX = r"^-\s+\[(?P<state>[ xX])\]\s+"
CHECKBOX = re.compile(CHECKBOX_PREFIX + r"(?P<text>.+)$")

_FENCE = "```"
_FENCE_OPEN = re.compile(r"^\s*(`{3,})([^`]*)$")
_FENCE_CLOSE = re.compile(r"^\s*(`{3,})\s*$")
_BACKTICKED = re.compile(r"`([^`]+)`")
_TRAILING_PUNCTUATION = re.compile(r"[.,;:!?]*")
_PATH_SEPARATORS = re.compile(r"[\\/]")
_EXEMPT_FIELD = re.compile(r"^\*\*Examination\*\*:\s*not-applicable\s*$")
_PARENT_SEGMENT = ".."


@dataclass
class ExaminationInputs:
    criteria: list[str] = field(default_factory=list)
    gherkin: list[str] = field(default_factory=list)
    run_commands: list[str] = field(default_factory=list)


class ScannedLine(NamedTuple):
    index: int  # position in the scanned input
    text: str  # right-stripped
    is_delimiter: bool  # an opening or closing fence line
    in_fence: bool  # True for lines between fence delimiters
    fence_index: int  # ordinal of the enclosing fence; -1 outside fences
    fence_info: str  # info string of the enclosing fence ("gherkin", ...)


def scan_fences(lines: Iterable[str]) -> Iterator[ScannedLine]:
    """Yield every line with its fenced-block context (CommonMark rules).

    A fence opens on a line of three or more backticks (no backtick in the
    info string) and closes only on a line of at least as many backticks and
    nothing else, so a 4-backtick fence can hold a 3-backtick line. Every
    reader of a plan's markdown uses this one scanner, so they agree on what
    is inside a fence.
    """
    fence_length, fence_info, fence_index = 0, "", -1
    for index, raw in enumerate(lines):
        text = raw.rstrip()
        if fence_length:
            closing = _FENCE_CLOSE.match(text)
            if closing and len(closing.group(1)) >= fence_length:
                yield ScannedLine(index, text, True, False, -1, "")
                fence_length = 0
                continue
            yield ScannedLine(index, text, False, True, fence_index, fence_info)
            continue
        opening = _FENCE_OPEN.match(text)
        if opening:
            fence_length, fence_index = len(opening.group(1)), fence_index + 1
            fence_info = opening.group(2).strip()
            yield ScannedLine(index, text, True, False, -1, "")
            continue
        yield ScannedLine(index, text, False, False, -1, "")


class _Line(NamedTuple):
    section: str  # title of the enclosing "## " heading; "" before the first
    text: str
    in_fence: bool
    fence_index: int
    fence_info: str


def _scan_lines(plan_text: str) -> Iterator[_Line]:
    """Yield every non-delimiter line with its section and fence context.

    Headings inside fenced blocks never change the section. Lines under the
    rendered `## Acceptance Examination` section are not inputs and are
    dropped, so that section's content can never move the digest.
    """
    section = ""
    for line in scan_fences(plan_text.splitlines()):
        if line.is_delimiter:
            continue
        if not line.in_fence and line.text.startswith("## "):
            section = line.text[3:].strip()
        if section == EXAMINATION_SECTION:
            continue
        yield _Line(
            section, line.text, line.in_fence, line.fence_index, line.fence_info
        )


def _criteria(lines: list[_Line]) -> list[str]:
    found: list[str] = []
    in_subheading = False
    for line in lines:
        if line.section != AC_SECTION or line.in_fence:
            continue
        if line.text.startswith("## "):
            in_subheading = False
        elif line.text.startswith("### "):
            in_subheading = True
        elif not in_subheading and (match := CHECKBOX.match(line.text)):
            found.append(match.group("text").strip())
    return found


def _gherkin(lines: list[_Line]) -> list[str]:
    # Every gherkin block under `## Slices`, in document order. Differs from
    # `scripts/lib/plan_parse.slice_gherkin_blocks` (first block per slice) on
    # purpose, and cannot reuse it: hooks/lib must not import scripts/lib.
    blocks: dict[int, list[str]] = {}
    for line in lines:
        if line.section == SLICES_SECTION and line.fence_info == GHERKIN_FENCE:
            blocks.setdefault(line.fence_index, []).append(line.text)
    return ["\n".join(body) for _, body in sorted(blocks.items())]


def _line_run_command(text: str) -> str | None:
    """The backticked span that ends `text` (trailing punctuation allowed)."""
    spans = list(_BACKTICKED.finditer(text))
    if not spans or not _TRAILING_PUNCTUATION.fullmatch(text[spans[-1].end() :]):
        return None
    command = spans[-1].group(1).strip()
    if not command or command.startswith(SKILL_COMMAND_PREFIX):
        return None
    return command


def _run_commands(lines: list[_Line]) -> list[str]:
    """One command per `## Pre-PR Quality Gate` line, checkbox or not."""
    commands = (
        _line_run_command(line.text)
        for line in lines
        if line.section == GATE_SECTION and not line.in_fence
    )
    return [command for command in commands if command]


def plan_examination_inputs(plan_text: str) -> ExaminationInputs:
    """The ordered criteria, Gherkin blocks and run commands of a plan."""
    lines = list(_scan_lines(plan_text))
    return ExaminationInputs(
        criteria=_criteria(lines),
        gherkin=_gherkin(lines),
        run_commands=_run_commands(lines),
    )


def criteria_ids(inputs: ExaminationInputs) -> list[str]:
    """The criterion ids, `AC1..ACn`, in the order of `inputs.criteria`."""
    return [f"{CRITERION_ID_PREFIX}{n}" for n in range(1, len(inputs.criteria) + 1)]


def inputs_digest(inputs: ExaminationInputs) -> str:
    """sha256 hex over canonical JSON of the three lists.

    Checkbox state is stripped by the parser, so ticking boxes, editing the
    status line, Build Progress or a rendered section never changes it.
    """
    canonical = json.dumps(
        {
            "criteria": inputs.criteria,
            "gherkin": inputs.gherkin,
            "run_commands": inputs.run_commands,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def render_inputs(inputs: ExaminationInputs, plan_id: str) -> str:
    """The block `/build` Step 7.6 pastes verbatim into the examiner prompt."""
    ids = criteria_ids(inputs)
    lines = [f"{cid}: {text}" for cid, text in zip(ids, inputs.criteria)]
    for block in inputs.gherkin:
        lines += ["", f"{_FENCE}{GHERKIN_FENCE}", block, _FENCE]
    if inputs.run_commands:
        lines += ["", "Run commands:"]
        lines += [f"- {command}" for command in inputs.run_commands]
    lines += ["", f"{PLAN_MARKER_PREFIX}{plan_id}"]
    return "\n".join(lines)


def parse_plan_marker(text: str) -> str | None:
    """The plan path named by the first `PLAN_MARKER_PREFIX` line, or `None`.

    Differs from `hooks/lib/review_verdicts.py::parse_scope_marker` on
    purpose: that marker carries a comma-separated file list and skips a
    prose line that quotes the prefix without one. This marker names exactly
    one plan, so the first line containing the prefix decides: an empty path
    or any `..` segment yields `None` rather than falling through to a later
    marker, because the path is later resolved against the repo root.
    """
    for line in text.splitlines():
        start = line.find(PLAN_MARKER_PREFIX)
        if start == -1:
            continue
        path = line[start + len(PLAN_MARKER_PREFIX) :].strip()
        if not path or _PARENT_SEGMENT in _PATH_SEPARATORS.split(path):
            return None
        return path
    return None


def is_exempt(plan_text: str) -> bool:
    """True when the plan header (before the first `## `) declares
    `**Examination**: not-applicable`."""
    for line in plan_text.splitlines():
        if line.startswith("## "):
            return False
        if _EXEMPT_FIELD.match(line.strip()):
            return True
    return False
