#!/usr/bin/env python3
"""plan_summary_record.py — record a step attempt's candidates in a plan.

Subcommand: record --plan <file> --step <N.M> --attempt <k> --result <json-file>

Writes one table row per candidate under the plan's `## Plan Review Summary`
-> `### Speculative dispatch` (plan decision 7). The module knows the
candidate row schema and nothing else about candidates; field validation is
`build_candidates_model.Candidate.from_dict`.

Not safe for concurrent runs on the same plan file; the caller serializes
record calls.

Exit codes:
  0  the plan was updated.
  1  invalid input: message on stderr, empty stdout, plan file untouched.
  2  usage error (argparse).

Stdlib only (ADR 0014, ADR 0015, ADR 0031).
"""

from __future__ import annotations

import argparse
import os
import re
import stat
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:  # sibling imports under -I / -P / PYTHONSAFEPATH
    sys.path.insert(0, _HERE)

from build_candidates_model import STEP_ID_RE, Candidate, DataError, load_json_object

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
METRIC_COLUMNS = COLUMNS[5:11]  # Suite .. Cost (USD): the cells a candidate fills
COST_DECIMALS = 4

OUTCOME_KEPT = "kept"
OUTCOME_NOT_DISPATCHED = "not dispatched"
OUTCOMES = (OUTCOME_KEPT, "removed", "disqualified", OUTCOME_NOT_DISPATCHED)

_FENCE_RE = re.compile(r"\s*(`{3,}|~{3,})(.*)")
_HEADING_RE = re.compile(r"(#{1,6}) +(.*?) *")
_LINE_RE = re.compile(r"[^\n]*\n|[^\n]+")
RESULT_SHAPE_HINT = "expected an object with a 'rows' list"


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


def _is_positive_int(value: object) -> bool:
    """A plain int (not a bool) that is at least 1."""
    return type(value) is int and value >= 1


def _parse_row(position: int, raw: object) -> _Row:
    label = f"row {position}"
    if not isinstance(raw, dict):
        _reject(f"{label}: not an object")
    outcome = raw.get("outcome")
    if outcome not in OUTCOMES:
        _reject(
            f"{label}: outcome must be one of {', '.join(OUTCOMES)}; got {outcome!r}"
        )
    reason = raw.get("reason")
    if not isinstance(reason, str):
        _reject(f"{label}: reason must be a string")
    if outcome == OUTCOME_NOT_DISPATCHED:
        row_id = raw.get("id")
        if not _is_positive_int(row_id):
            _reject(f"{label}: id must be a positive int")
        return _Row(row_id, outcome, reason, None, None)
    candidate = Candidate.from_dict(raw)
    rank = raw.get("rank")
    if not _is_positive_int(rank):
        _reject(f"candidate {candidate.id}: rank must be an int >= 1")
    return _Row(candidate.id, outcome, reason, candidate, rank)


def _parse_rows(raw_rows: object) -> list[_Row]:
    """Validated rows in candidate-id order; at most one is `kept`."""
    if not isinstance(raw_rows, list):
        _reject("rows must be a list")
    if not raw_rows:
        _reject("rows must not be empty")
    rows = sorted(
        (_parse_row(position, raw) for position, raw in enumerate(raw_rows, start=1)),
        key=lambda row: row.id,
    )
    seen: set[int] = set()
    for row in rows:
        if row.id in seen:
            _reject(f"duplicate candidate id {row.id}")
        seen.add(row.id)
    kept_ids = [str(row.id) for row in rows if row.outcome == OUTCOME_KEPT]
    if len(kept_ids) > 1:
        _reject(f"more than one kept row: candidates {', '.join(kept_ids)}")
    return rows


def _text_cell(text: str) -> str:
    """`text` made safe for one table cell: a line break would split the row
    (and could forge a heading), so it is rejected; a backslash and then a
    pipe are escaped, in that order, so `\\|` cannot read as an escaped pipe."""
    if "\n" in text or "\r" in text:
        _reject(f"cell text must be a single line: {text!r}")
    return text.replace("\\", "\\\\").replace("|", "\\|")


def _metric_cells(row: _Row) -> list[str]:
    """The `METRIC_COLUMNS` cells: Suite, Scenarios met, Errors, Warnings,
    Diff lines and Cost (USD)."""
    candidate = row.candidate
    if candidate is None:
        return [EM_DASH] * len(METRIC_COLUMNS)
    return [
        "green" if candidate.suite_green else "red",
        f"{candidate.scenarios_met}/{candidate.scenarios_total}",
        str(candidate.errors),
        str(candidate.warnings),
        str(candidate.diff_lines),
        f"{candidate.cost_usd:.{COST_DECIMALS}f}",
    ]


def _branch_cell(candidate: Candidate | None) -> str:
    if candidate is None or candidate.branch == "":
        return EM_DASH
    return _text_cell(candidate.branch)


def _render_row_line(step: str, attempt: int, row: _Row, eol: str) -> str:
    cells = [
        step,
        str(attempt),
        EM_DASH if row.rank is None else str(row.rank),
        str(row.id),
        _branch_cell(row.candidate),
        *_metric_cells(row),
        row.outcome,
        _text_cell(row.reason),
    ]
    return _join_cells(cells, eol)


def _join_cells(cells: list[str], eol: str) -> str:
    return "| " + " | ".join(cells) + " |" + eol


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
    """Lines with their line ending kept; unlike str.splitlines, only "\\n"
    splits."""
    return _LINE_RE.findall(text)


def _line_ending(lines: list[str]) -> str:
    """The plan's line ending, taken from its first line: "\\r\\n" when that
    line ends in it, else "\\n"."""
    return "\r\n" if lines and lines[0].endswith("\r\n") else "\n"


def _fence_after(open_fence: str | None, text: str) -> str | None:
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


def _headings(lines: list[str]) -> list[_Heading]:
    """Every ATX heading at column 0 with a space after the hashes, outside a
    fence; a `# ` heading ends a `## ` section too. A fence that is never
    closed runs to the end of the file (as in CommonMark), so nothing after it
    is a heading and a summary appended there lands inside the fence."""
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


def _splice(lines: list[str], start: int, end: int, new: list[str], eol: str) -> str:
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


def _blank_line_before(lines: list[str], index: int, eol: str) -> list[str]:
    """A blank line to put between `lines[index - 1]` and a block inserted at
    `index`, unless one is already there."""
    return [eol] if index > 0 and lines[index - 1].strip() else []


def _table_lines(row_lines: list[str], eol: str) -> list[str]:
    header = _join_cells(list(COLUMNS), eol)
    separator = _join_cells(["---"] * len(COLUMNS), eol)
    return [header, separator, *row_lines]


def _subsection_lines(table: list[str], eol: str) -> list[str]:
    return [f"{'#' * SUBSECTION_LEVEL} {SUBSECTION_TITLE}{eol}", eol, *table]


def _insert_summary(
    lines: list[str], headings: list[_Heading], table: list[str], eol: str
) -> str:
    """No summary yet: a whole section before Build Progress, else at the end
    of the file."""
    summary = [
        f"{'#' * SUMMARY_LEVEL} {SUMMARY_TITLE}{eol}",
        eol,
        *_subsection_lines(table, eol),
    ]
    build_progress = _find_section(
        headings, len(lines), SUMMARY_LEVEL, BUILD_PROGRESS_TITLE
    )
    if build_progress is None:
        index = len(lines)
        block = _blank_line_before(lines, index, eol) + summary
        return _splice(lines, index, index, block, eol)
    index = build_progress.start
    block = _blank_line_before(lines, index, eol) + summary + [eol]
    return _splice(lines, index, index, block, eol)


def _table_span(lines: list[str], section: _Section) -> tuple[int, int] | None:
    """`(start, end)` of the first run of table lines inside `section`."""
    start = next(
        (
            index
            for index in range(section.start + 1, section.end)
            if lines[index].lstrip().startswith("|")
        ),
        None,
    )
    if start is None:
        return None
    end = start
    while end < section.end and lines[end].lstrip().startswith("|"):
        end += 1
    return start, end


def _row_key(line: str) -> tuple[str, str]:
    """The Step and Attempt cells of a table row."""
    cells = line.strip().strip("|").split("|")
    return (cells[0].strip(), cells[1].strip()) if len(cells) > 1 else ("", "")


def _merge_rows(
    existing: list[str], step: str, attempt: int, new_row_lines: list[str], eol: str
) -> list[str]:
    """`existing` data rows with every row of this step and attempt replaced
    by `new_row_lines` at the first such row's position; `new_row_lines`
    follow the last row when none matches."""
    key = (step, str(attempt))
    complete = [line if line.endswith("\n") else line + eol for line in existing]
    merged: list[str] = []
    is_placed = False
    for line in complete:
        if _row_key(line) != key:
            merged.append(line)
        elif not is_placed:
            merged.extend(new_row_lines)
            is_placed = True
    return merged if is_placed else complete + new_row_lines


def _merge_into_subsection(
    lines: list[str],
    subsection: _Section,
    step: str,
    attempt: int,
    new_row_lines: list[str],
    eol: str,
) -> str:
    span = _table_span(lines, subsection)
    if span is None:  # a hand-made subsection with no table yet
        end = _content_end(lines, subsection)
        block = [eol, *_table_lines(new_row_lines, eol)]
        return _splice(lines, end, end, block, eol)
    start, end = span  # the header and separator never match a step N.M
    merged = _merge_rows(lines[start:end], step, attempt, new_row_lines, eol)
    return _splice(lines, start, end, merged, eol)


def _check_step_and_attempt(step: object, attempt: object) -> None:
    if not (isinstance(step, str) and STEP_ID_RE.fullmatch(step)):
        _reject(f"step must be N.M (digits, a dot, digits); got {step!r}")
    if not _is_positive_int(attempt):
        _reject(f"attempt must be a positive integer; got {attempt!r}")


def record(plan_text: str, step: str, attempt: int, rows: list[dict]) -> str:
    """`plan_text` with the rows of step `step`, attempt `attempt` recorded
    under `## Plan Review Summary` -> `### Speculative dispatch`; raise
    ValueError for input the plan cannot take. Inserted lines use the plan's
    own line ending. Not safe for concurrent runs on the same plan file; the
    caller serializes record calls."""
    _check_step_and_attempt(step, attempt)
    lines = _split_lines(plan_text)
    eol = _line_ending(lines)
    new_row_lines = [
        _render_row_line(step, attempt, row, eol) for row in _parse_rows(rows)
    ]
    table = _table_lines(new_row_lines, eol)
    headings = _headings(lines)
    summary = _find_section(headings, len(lines), SUMMARY_LEVEL, SUMMARY_TITLE)
    if summary is None:
        return _insert_summary(lines, headings, table, eol)
    subsection = _find_section(
        headings, len(lines), SUBSECTION_LEVEL, SUBSECTION_TITLE, within=summary
    )
    if subsection is None:
        end = _content_end(lines, summary)
        block = [eol, *_subsection_lines(table, eol)]
        return _splice(lines, end, end, block, eol)
    return _merge_into_subsection(lines, subsection, step, attempt, new_row_lines, eol)


# --- command line -----------------------------------------------------------


def _read_plan(path: Path) -> str:
    try:
        return path.read_bytes().decode("utf-8")
    except FileNotFoundError:
        raise ValueError(f"plan file: no such file: {path}") from None
    except OSError as exc:
        raise ValueError(f"plan file: cannot read {path}: {exc.strerror}") from None
    except UnicodeDecodeError:
        raise ValueError(f"plan file: not valid UTF-8: {path}") from None


def _load_rows(path: str) -> object:
    """The `rows` value of the result file."""
    try:
        data = load_json_object(path, "result")
    except DataError as exc:
        raise ValueError(f"{exc} ({RESULT_SHAPE_HINT})") from None
    if "rows" not in data:
        _reject(f"result: no 'rows' key: {path} ({RESULT_SHAPE_HINT})")
    return data["rows"]


def _coerce_attempt(raw: str) -> object:
    """`raw` as an int when it is ASCII digits, else unchanged for `record`
    to reject; a digit string too long for int() is also left unchanged."""
    if not re.fullmatch(r"[0-9]+", raw):
        return raw
    try:
        return int(raw)
    except ValueError:  # beyond sys.get_int_max_str_digits()
        return raw


def _write_atomic(target: Path, data: bytes) -> None:
    """Replace `target` with `data` through a same-directory temp file, so a
    crash never leaves a truncated plan; the file keeps its mode. Follows
    `gherkin_stub_merge._write_atomic`."""
    mode = stat.S_IMODE(target.stat().st_mode)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(target.parent), prefix=f".{target.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "wb") as tmp_file:
            tmp_file.write(data)
            os.chmod(tmp_name, mode)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        os.replace(tmp_name, target)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def _cmd_record(args: argparse.Namespace) -> int:
    try:
        target = Path(args.plan).resolve()  # a symlinked plan updates its target
        rows = _load_rows(args.result)
        plan_text = _read_plan(target)
        updated = record(plan_text, args.step, _coerce_attempt(args.attempt), rows)
        _write_atomic(target, updated.encode("utf-8"))
    except (OSError, ValueError) as exc:
        print(f"record: {exc}", file=sys.stderr)
        return EXIT_INVALID_INPUT
    return EXIT_OK


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="plan_summary_record.py",
        description="Record a step attempt's candidates in a plan.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    recording = sub.add_parser("record", help="record one step attempt's rows")
    recording.add_argument("--plan", required=True, help="plan file to update")
    recording.add_argument(
        "--step", required=True, help="plan step, as N.M (digits, a dot, digits)"
    )
    recording.add_argument(
        "--attempt", required=True, help="attempt, a positive integer"
    )
    recording.add_argument("--result", required=True, help='JSON file: {"rows": [...]}')
    recording.set_defaults(handler=_cmd_record)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
