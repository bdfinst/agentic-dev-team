#!/usr/bin/env python3
"""plan_summary_record.py — record a step attempt's candidates in a plan.

Subcommand: record --plan <file> --step <N.M> --attempt <k> --result <json-file>

Writes one table row per candidate under the plan's `## Plan Review Summary`
-> `### Speculative dispatch` (plan #2273, decision 7). The module knows the
candidate row schema and nothing else about candidates; field validation is
`build_candidates.Candidate.from_dict`.

Exit codes:
  0  the plan was updated.
  1  invalid input: message on stderr, empty stdout, plan file untouched.
  2  usage error (argparse).

Stdlib only (ADR 0014, ADR 0015, ADR 0031).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:  # sibling imports under -I / -P / PYTHONSAFEPATH
    sys.path.insert(0, _HERE)

from build_candidates import Candidate

EXIT_OK = 0
EXIT_INVALID_INPUT = 1

SUMMARY_LEVEL = 2
SUMMARY_TITLE = "Plan Review Summary"
BUILD_PROGRESS_TITLE = "Build Progress"
SUBSECTION_LEVEL = 3
SUBSECTION_TITLE = "Speculative dispatch"

COLUMNS = (
    "Step",
    "Attempt",
    "Rank",
    "Candidate",
    "Branch",
    "Suite",
    "Scenarios met",
    "Errors",
    "Warnings",
    "Diff lines",
    "Cost (USD)",
    "Outcome",
    "Reason",
)
EM_DASH = "—"
COST_DECIMALS = 4

OUTCOME_KEPT = "kept"
OUTCOME_NOT_DISPATCHED = "not dispatched"
OUTCOMES = (OUTCOME_KEPT, "removed", "disqualified", OUTCOME_NOT_DISPATCHED)

_FENCE_RE = re.compile(r"\s*(`{3,}|~{3,})(.*)")
_HEADING_RE = re.compile(r"(#{1,6}) +(.*?) *")
_LINE_RE = re.compile(r"[^\n]*\n|[^\n]+")


# --- rows -------------------------------------------------------------------


@dataclass(frozen=True)
class _Row:
    """One validated result row: `candidate` and `rank` are None for a
    `not dispatched` row."""

    id: int
    outcome: str
    reason: str
    candidate: Candidate | None
    rank: int | None


def _reject(message: str) -> NoReturn:
    raise ValueError(message)


def _parse_row(position: int, raw: object) -> _Row:
    label = f"row {position}"
    if not isinstance(raw, dict):
        _reject(f"{label}: not an object")
    outcome = raw.get("outcome")
    if outcome not in OUTCOMES:
        raise ValueError(
            f"{label}: outcome must be one of {', '.join(OUTCOMES)}; got {outcome!r}"
        )
    reason = raw.get("reason")
    if not isinstance(reason, str):
        _reject(f"{label}: reason must be a string")
    if outcome == OUTCOME_NOT_DISPATCHED:
        row_id = raw.get("id")
        if not (type(row_id) is int and row_id >= 1):
            raise ValueError(f"{label}: id must be a positive int")
        return _Row(row_id, outcome, reason, None, None)
    candidate = Candidate.from_dict(raw)
    rank = raw.get("rank")
    if not (type(rank) is int and rank >= 1):
        raise ValueError(f"candidate {candidate.id}: rank must be an int >= 1")
    return _Row(candidate.id, outcome, reason, candidate, rank)


def _parse_rows(raw_rows: object) -> list[_Row]:
    if not isinstance(raw_rows, list):
        _reject("rows must be a list")
    return sorted(
        (_parse_row(position, raw) for position, raw in enumerate(raw_rows, start=1)),
        key=lambda row: row.id,
    )


def _text_cell(text: str) -> str:
    """`text` made safe for one table cell: a line break would split the row
    (and could forge a heading), so it is rejected; a pipe is escaped."""
    if "\n" in text or "\r" in text:
        raise ValueError(f"cell text must be a single line: {text!r}")
    return text.replace("|", "\\|")


def _metric_cells(row: _Row) -> list[str]:
    """Suite, Scenarios met, Errors, Warnings, Diff lines and Cost (USD)."""
    candidate = row.candidate
    if candidate is None:
        return [EM_DASH] * 6
    return [
        "green" if candidate.suite_green else "red",
        f"{candidate.scenarios_met}/{candidate.scenarios_total}",
        str(candidate.errors),
        str(candidate.warnings),
        str(candidate.diff_lines),
        f"{candidate.cost_usd:.{COST_DECIMALS}f}",
    ]


def _render_row(step: str, attempt: int, row: _Row) -> str:
    candidate = row.candidate
    cells = [
        step,
        str(attempt),
        EM_DASH if row.rank is None else str(row.rank),
        str(row.id),
        EM_DASH if candidate is None else _text_cell(candidate.branch),
        *_metric_cells(row),
        row.outcome,
        _text_cell(row.reason),
    ]
    return _join_cells(cells)


def _join_cells(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |\n"


# --- document structure -----------------------------------------------------


@dataclass(frozen=True)
class _Heading:
    index: int
    level: int
    title: str


@dataclass(frozen=True)
class _Section:
    """Lines `start` (the heading) up to but excluding `end`."""

    start: int
    end: int


def _split_lines(text: str) -> list[str]:
    """Lines with their "\\n" kept; unlike str.splitlines, only "\\n" splits."""
    return _LINE_RE.findall(text)


def _fence_after(open_fence: str | None, text: str) -> str | None:
    """The fence marker still open after `text`, given `open_fence` before."""
    fence = _FENCE_RE.fullmatch(text)
    if fence is None:
        return open_fence
    marker, info = fence.groups()
    if open_fence is None:
        return marker
    closes = (
        marker[0] == open_fence[0]
        and len(marker) >= len(open_fence)
        and not info.strip()
    )
    return None if closes else open_fence


def _headings(lines: list[str]) -> list[_Heading]:
    """Every Markdown heading that is not inside a ``` or ~~~ fenced block."""
    found = []
    open_fence = None
    for index, line in enumerate(lines):
        text = line.rstrip("\r\n")
        was_open = open_fence is not None
        open_fence = _fence_after(open_fence, text)
        if was_open or open_fence is not None:
            continue
        heading = _HEADING_RE.fullmatch(text)
        if heading:
            found.append(_Heading(index, len(heading.group(1)), heading.group(2)))
    return found


def _find_section(
    headings: list[_Heading],
    line_count: int,
    level: int,
    title: str,
    within: _Section | None = None,
) -> _Section | None:
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
            return _Section(heading.index, end)
    return None


def _content_end(lines: list[str], section: _Section) -> int:
    """Index just after the section's last non-blank line."""
    end = section.end
    while end > section.start + 1 and not lines[end - 1].strip():
        end -= 1
    return end


def _splice(lines: list[str], start: int, end: int, new: list[str]) -> str:
    """`lines` with `lines[start:end]` replaced by `new`. A line left without
    its newline gets one; when only blank lines follow, they are dropped so
    the file ends with exactly one newline."""
    head = lines[:start]
    if head and not head[-1].endswith("\n"):
        head[-1] += "\n"
    tail = lines[end:]
    if not any(line.strip() for line in tail):
        tail = []
    return "".join(head + new + tail)


def _blank_line_before(lines: list[str], index: int) -> list[str]:
    """A blank line to put between `lines[index - 1]` and a block inserted at
    `index`, unless one is already there."""
    return ["\n"] if index > 0 and lines[index - 1].strip() else []


def _table_lines(rendered_rows: list[str]) -> list[str]:
    header = _join_cells(list(COLUMNS))
    separator = _join_cells(["---"] * len(COLUMNS))
    return [header, separator, *rendered_rows]


def _subsection_lines(table: list[str]) -> list[str]:
    return [f"{'#' * SUBSECTION_LEVEL} {SUBSECTION_TITLE}\n", "\n", *table]


def _insert_summary(
    lines: list[str], headings: list[_Heading], table: list[str]
) -> str:
    """No summary yet: a whole section before Build Progress, else at the end
    of the file."""
    summary = [
        f"{'#' * SUMMARY_LEVEL} {SUMMARY_TITLE}\n",
        "\n",
        *_subsection_lines(table),
    ]
    build_progress = _find_section(
        headings, len(lines), SUMMARY_LEVEL, BUILD_PROGRESS_TITLE
    )
    if build_progress is None:
        index = len(lines)
        return _splice(lines, index, index, _blank_line_before(lines, index) + summary)
    index = build_progress.start
    block = _blank_line_before(lines, index) + summary + ["\n"]
    return _splice(lines, index, index, block)


def record(plan_text: str, step: str, attempt: int, rows: list[dict]) -> str:
    """`plan_text` with the rows of step `step`, attempt `attempt` recorded
    under `## Plan Review Summary` -> `### Speculative dispatch`; raise
    ValueError for input the plan cannot take."""
    parsed = _parse_rows(rows)
    table = _table_lines([_render_row(step, attempt, row) for row in parsed])
    lines = _split_lines(plan_text)
    headings = _headings(lines)
    summary = _find_section(headings, len(lines), SUMMARY_LEVEL, SUMMARY_TITLE)
    if summary is None:
        return _insert_summary(lines, headings, table)
    subsection = _find_section(
        headings, len(lines), SUBSECTION_LEVEL, SUBSECTION_TITLE, within=summary
    )
    if subsection is None:
        end = _content_end(lines, summary)
        return _splice(lines, end, end, ["\n", *_subsection_lines(table)])
    raise ValueError("an existing Speculative dispatch subsection is not handled yet")


# --- command line -----------------------------------------------------------


def _cmd_record(args: argparse.Namespace) -> int:
    try:
        data = json.loads(Path(args.result).read_text(encoding="utf-8"))
        plan_text = Path(args.plan).read_bytes().decode("utf-8")
        updated = record(plan_text, args.step, args.attempt, data["rows"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"record: {exc}", file=sys.stderr)
        return EXIT_INVALID_INPUT
    Path(args.plan).write_bytes(updated.encode("utf-8"))
    return EXIT_OK


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="plan_summary_record.py",
        description="Record a step attempt's candidates in a plan.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    recording = sub.add_parser("record", help="record one step attempt's rows")
    recording.add_argument("--plan", required=True, help="plan file to update")
    recording.add_argument("--step", required=True, help="plan step, as N.M")
    recording.add_argument("--attempt", required=True, type=int, help="attempt number")
    recording.add_argument("--result", required=True, help='JSON file: {"rows": [...]}')
    recording.set_defaults(handler=_cmd_record)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
