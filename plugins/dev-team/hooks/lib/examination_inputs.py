"""Examination inputs for the acceptance examiner (#2270).

Pure, stdlib only, no I/O. The code here is the single source of criteria
numbering: ids are `AC1..ACn` by position in `plan_examination_inputs`.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import NamedTuple

AC_SECTION = "Acceptance Criteria"
SLICES_SECTION = "Slices"
GATE_SECTION = "Pre-PR Quality Gate"
GHERKIN_FENCE = "gherkin"
SKILL_COMMAND_PREFIX = "/"
PLAN_MARKER_PREFIX = "Acceptance-examination plan: "

_CHECKBOX = re.compile(r"^-\s+\[[ xX]\]\s+(.+)$")
_FENCE = "```"
_BACKTICKED = re.compile(r"`([^`]+)`")
_PATH_SEPARATORS = re.compile(r"[\\/]")
_EXEMPT_FIELD = re.compile(r"^\*\*Examination\*\*:\s*not-applicable\s*$")
_PARENT_SEGMENT = ".."


@dataclass
class ExaminationInputs:
    criteria: list[str] = field(default_factory=list)
    gherkin: list[str] = field(default_factory=list)
    run_commands: list[str] = field(default_factory=list)


class _Line(NamedTuple):
    section: str  # title of the enclosing "## " heading; "" before the first
    text: str
    in_fence: bool  # True for lines between fence delimiters
    fence_index: int  # ordinal of the enclosing fence; -1 outside fences
    fence_info: str  # info string of the enclosing fence ("gherkin", ...)


def _scan_lines(plan_text: str) -> Iterator[_Line]:
    """Yield every non-delimiter line with its section and fence context.

    Headings inside fenced blocks never change the section.
    """
    section, fence_info, fence_index = "", None, -1
    for raw in plan_text.splitlines():
        text = raw.rstrip()
        if text.lstrip().startswith(_FENCE):
            fence_index, fence_info = _toggle_fence(fence_index, fence_info, text)
            continue
        if fence_info is None and text.startswith("## "):
            section = text[3:].strip()
        in_fence = fence_info is not None
        yield _Line(
            section, text, in_fence, fence_index if in_fence else -1, fence_info or ""
        )


def _toggle_fence(
    index: int, info: str | None, delimiter: str
) -> tuple[int, str | None]:
    if info is not None:
        return index, None
    return index + 1, delimiter.lstrip()[len(_FENCE) :].strip()


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
        elif not in_subheading and (match := _CHECKBOX.match(line.text)):
            found.append(match.group(1).strip())
    return found


def _gherkin(lines: list[_Line]) -> list[str]:
    blocks: dict[int, list[str]] = {}
    for line in lines:
        if line.section == SLICES_SECTION and line.fence_info == GHERKIN_FENCE:
            blocks.setdefault(line.fence_index, []).append(line.text)
    return ["\n".join(body) for _, body in sorted(blocks.items())]


def _run_commands(lines: list[_Line]) -> list[str]:
    commands: list[str] = []
    for line in lines:
        if (
            line.section != GATE_SECTION
            or line.in_fence
            or not _CHECKBOX.match(line.text)
        ):
            continue
        for candidate in _BACKTICKED.findall(line.text):
            command = candidate.strip()
            if command and not command.startswith(SKILL_COMMAND_PREFIX):
                commands.append(command)
    return commands


def plan_examination_inputs(plan_text: str) -> ExaminationInputs:
    """The ordered criteria, Gherkin blocks and run commands of a plan."""
    lines = list(_scan_lines(plan_text))
    return ExaminationInputs(
        criteria=_criteria(lines),
        gherkin=_gherkin(lines),
        run_commands=_run_commands(lines),
    )


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
    lines = [f"AC{n}: {text}" for n, text in enumerate(inputs.criteria, start=1)]
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
