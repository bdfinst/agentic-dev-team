"""Delta-scoping and checkpoint-abort metrics.

Skip rate reads consult rows only: dispatch-hook rows count pairs the consult
left to dispatch, so adding them would measure the wrong thing. Abort yield
counts only the lenses an aborted checkpoint deferred. Read-only.

Stdlib-only.
"""

from __future__ import annotations

from session_log import classify as session_classify

from . import formatting, streams
from .formatting import ReportContext, ReportLine, ReportNote
from .prereg import Metric

CONSULT = "consult"
CHECKPOINT = "checkpoint"
STOP_HOOK = "stop-hook"
ABORT_MODE = "abort"
MISSING_SCOPE_MARKER = "missing-scope-marker"
#: Boundary events are not a benefit instrument, so they are not in the stream table.
BOUNDARY_EVENTS = streams.StreamSpec(
    "boundary-events",
    "boundary-events.jsonl",
    streams.ID_BEARING,
    "project",
    "ts",
    True,
)
_NO_BACKSTOP_FIELD = "per backstop: not recorded in the rows"


def _count(row: streams.Row, name: str) -> int:
    value = row.data.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise streams.InputError(
            row.file,
            row.line,
            f"row field '{name}' is not a non-negative integer",
            "repair or remove that row; the evaluation never edits the file",
        )
    return value


def _lens_list(row: streams.Row) -> list[str]:
    lenses = row.data.get("deferred_lenses")
    if not isinstance(lenses, list) or not all(
        isinstance(lens, str) for lens in lenses
    ):
        raise streams.InputError(
            row.file,
            row.line,
            "row field 'deferred_lenses' is not a list of names",
            "repair or remove that row; the evaluation never edits the file",
        )
    return lenses


def skip_rate(metric: Metric, ctx: ReportContext) -> ReportLine:
    part = ctx.partition(metric.instrument)
    is_consult = lambda row: row.data.get("source") == CONSULT
    consults = [row for row in part.real if is_consult(row)]
    candidates = sum(_count(row, "candidate_pairs") for row in consults)
    skipped = sum(_count(row, "skipped_pairs") for row in consults)
    first_runs, repeat_runs = _split_first_and_repeat(consults)
    ceiling = (
        [f"theoretical ceiling {formatting.number_text(metric.ceiling)}%"]
        if metric.ceiling is not None
        else []
    )
    return formatting.rate_line(
        metric,
        skipped,
        candidates,
        {row.data["session_id"] for row in consults},
        sum(map(is_consult, part.unverified)),
        details=ceiling,
        value_details=[
            _run_split_text("first runs", first_runs),
            _run_split_text("repeat runs", repeat_runs),
            _NO_BACKSTOP_FIELD,
        ],
    )


def _split_first_and_repeat(consults: list[streams.Row]) -> tuple[list, list]:
    """A session's first consult is a first run; each later one is a repeat run."""
    seen: set[str] = set()
    first, repeat = [], []
    for row in sorted(consults, key=lambda r: (r.data["ts"], str(r.file), r.line)):
        session = row.data["session_id"]
        (repeat if session in seen else first).append(row)
        seen.add(session)
    return first, repeat


def _run_split_text(label: str, rows: list[streams.Row]) -> str:
    candidates = sum(_count(row, "candidate_pairs") for row in rows)
    skipped = sum(_count(row, "skipped_pairs") for row in rows)
    return f"{label}: " + (
        formatting.rate_text(skipped, candidates)
        if candidates
        else "no candidate pairs"
    )


def abort_yield(metric: Metric, ctx: ReportContext) -> ReportLine:
    """Share of the lenses an aborted checkpoint deferred whose own result later tripped the abort rule.

    A deferred lens counts as having found something new when a stop-hook row in the same session,
    at or after the abort, names it as the lens whose result alone tripped the rule."""
    part = ctx.partition(metric.instrument)
    aborts = [r for r in part.real if _is_aborted_checkpoint(r)]
    tripped = [
        (
            r.data["session_id"],
            r.data["ts"],
            session_classify.strip_ns(r.data["triggering_agent"]),
        )
        for r in part.real
        if r.data.get("source") == STOP_HOOK
        and r.data.get("aborted") is True
        and isinstance(r.data.get("triggering_agent"), str)
    ]
    deferred = found = 0
    for row in aborts:
        for lens in map(session_classify.strip_ns, _lens_list(row)):
            deferred += 1
            found += any(
                session == row.data["session_id"]
                and ts >= row.data["ts"]
                and agent == lens
                for session, ts, agent in tripped
            )
    return formatting.rate_line(
        metric,
        found,
        deferred,
        {r.data["session_id"] for r in aborts},
        sum(map(_is_aborted_checkpoint, part.unverified)),
    )


def _is_aborted_checkpoint(row: streams.Row) -> bool:
    return (
        row.data.get("source") == CHECKPOINT
        and row.data.get("mode") == ABORT_MODE
        and row.data.get("aborted") is True
    )


def missing_scope_marker_split(skip_metric: Metric, ctx: ReportContext) -> ReportNote:
    """Missing-scope-marker events split by whether the session ran a consult.

    The event carries no dispatch source, so a session with a real consult row is ``consult`` and one
    without is ``direct``."""
    consult_sessions = {
        row.data["session_id"]
        for row in ctx.partition(skip_metric.instrument).real
        if row.data.get("source") == CONSULT
    }
    rows = streams.rows_in_window(
        streams.load_rows(BOUNDARY_EVENTS, ctx.sources),
        BOUNDARY_EVENTS.ts_field,
        ctx.start,
        ctx.end,
    )
    part = streams.partition_rows(
        [r for r in rows if r.data.get("matched_rule") == MISSING_SCOPE_MARKER],
        ctx.index,
    )
    consult = sum(r.data["session_id"] in consult_sessions for r in part.real)
    direct = len(part.real) - consult
    return ReportNote(
        MISSING_SCOPE_MARKER,
        (
            f"{MISSING_SCOPE_MARKER}: direct={direct} consult={consult}",
            f"  unverified: {len(part.unverified)}",
        ),
        {"direct": direct, "consult": consult, "unverified": len(part.unverified)},
    )
