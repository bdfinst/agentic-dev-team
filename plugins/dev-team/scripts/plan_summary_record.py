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
from plan_markdown import (
    Heading,
    Section,
    blank_line_before,
    content_end,
    find_headings,
    find_section,
    line_ending,
    splice,
    split_lines,
)

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
METRIC_COLUMNS = COLUMNS[
    COLUMNS.index("Suite") : COLUMNS.index("Cost (USD)") + 1
]  # Suite .. Cost (USD): the cells a candidate fills
COST_DECIMALS = 4

OUTCOME_KEPT = "kept"
OUTCOME_NOT_DISPATCHED = "not dispatched"
OUTCOMES = (OUTCOME_KEPT, "removed", "disqualified", OUTCOME_NOT_DISPATCHED)

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
    if outcome == OUTCOME_KEPT and candidate.is_disqualified:
        _reject(
            f"candidate {candidate.id}: kept but disqualified "
            f"({candidate.disqualification_reason})"
        )
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


def _table_lines(row_lines: list[str], eol: str) -> list[str]:
    header = _join_cells(list(COLUMNS), eol)
    separator = _join_cells(["---"] * len(COLUMNS), eol)
    return [header, separator, *row_lines]


def _subsection_lines(table: list[str], eol: str) -> list[str]:
    return [f"{'#' * SUBSECTION_LEVEL} {SUBSECTION_TITLE}{eol}", eol, *table]


def _insert_summary(
    lines: list[str], headings: list[Heading], table: list[str], eol: str
) -> str:
    """No summary yet: a whole section before Build Progress, else at the end
    of the file."""
    summary = [
        f"{'#' * SUMMARY_LEVEL} {SUMMARY_TITLE}{eol}",
        eol,
        *_subsection_lines(table, eol),
    ]
    build_progress = find_section(
        headings, len(lines), SUMMARY_LEVEL, BUILD_PROGRESS_TITLE
    )
    if build_progress is None:
        index = len(lines)
        block = blank_line_before(lines, index, eol) + summary
        return splice(lines, index, index, block, eol)
    index = build_progress.start
    block = blank_line_before(lines, index, eol) + summary + [eol]
    return splice(lines, index, index, block, eol)


def _table_span(lines: list[str], section: Section) -> tuple[int, int] | None:
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
    subsection: Section,
    step: str,
    attempt: int,
    new_row_lines: list[str],
    eol: str,
) -> str:
    span = _table_span(lines, subsection)
    if span is None:  # a hand-made subsection with no table yet
        end = content_end(lines, subsection)
        block = [eol, *_table_lines(new_row_lines, eol)]
        return splice(lines, end, end, block, eol)
    start, end = span  # the header and separator never match a step N.M
    merged = _merge_rows(lines[start:end], step, attempt, new_row_lines, eol)
    return splice(lines, start, end, merged, eol)


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
    lines = split_lines(plan_text)
    eol = line_ending(lines)
    new_row_lines = [
        _render_row_line(step, attempt, row, eol) for row in _parse_rows(rows)
    ]
    table = _table_lines(new_row_lines, eol)
    headings = find_headings(lines)
    summary = find_section(headings, len(lines), SUMMARY_LEVEL, SUMMARY_TITLE)
    if summary is None:
        return _insert_summary(lines, headings, table, eol)
    subsection = find_section(
        headings, len(lines), SUBSECTION_LEVEL, SUBSECTION_TITLE, within=summary
    )
    if subsection is None:
        end = content_end(lines, summary)
        block = [eol, *_subsection_lines(table, eol)]
        return splice(lines, end, end, block, eol)
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
    """The `rows` value of the result file. The shape hint is added only when
    the file parsed but has the wrong shape."""
    try:
        data = load_json_object(path, "result")
    except DataError as exc:
        hint = (
            f" ({RESULT_SHAPE_HINT})"
            if "JSON root is not an object" in str(exc)
            else ""
        )
        raise ValueError(f"{exc}{hint}") from None
    if "rows" not in data:
        _reject(f"result: no 'rows' key: {path} ({RESULT_SHAPE_HINT})")
    return data["rows"]


#: An attempt number never needs more digits than this; longer digit strings
#: are left to `record` to reject, without depending on the interpreter's
#: int-string digit limit (absent before 3.10.7, off under
#: PYTHONINTMAXSTRDIGITS=0).
_ATTEMPT_MAX_DIGITS = 9
_ATTEMPT_RE = re.compile(rf"[0-9]{{1,{_ATTEMPT_MAX_DIGITS}}}")


def _coerce_attempt(raw: str) -> object:
    """`raw` as an int when it is at most `_ATTEMPT_MAX_DIGITS` ASCII digits,
    else unchanged for `record` to reject."""
    if not _ATTEMPT_RE.fullmatch(raw):
        return raw
    return int(raw)


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
