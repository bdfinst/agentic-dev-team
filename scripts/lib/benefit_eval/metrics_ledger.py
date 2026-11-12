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
_NO_BACKSTOP_FIELD = "per backstop: not recorded in the rows"
COUNTING_DEFECT = "counting defect: the measured rate is above the theoretical ceiling"


def _count(row: streams.Row, name: str) -> int:
    return streams.row_field(row, name, int, minimum=0)


def _lens_list(row: streams.Row) -> list[str]:
    return streams.row_field(row, "deferred_lenses", list, items=str, noun="a list of names")


def skip_rate(metric: Metric, ctx: ReportContext) -> ReportLine:
    part = ctx.partition(metric.instrument)
    is_consult = lambda row: row.data.get("source") == CONSULT
    consults = [row for row in part.real if is_consult(row)]
    candidates = sum(_count(row, "candidate_pairs") for row in consults)
    skipped = sum(_count(row, "skipped_pairs") for row in consults)
    first_runs, repeat_runs = _split_first_and_repeat(
        consults, streams.STREAM_TABLE[metric.instrument].ts_field
    )
    ceiling = (
        [f"theoretical ceiling {formatting.number_text(metric.ceiling)}%"]
        if metric.ceiling is not None
        else []
    )
    rate = formatting.percent(skipped, candidates)
    counting_defect = (
        [COUNTING_DEFECT]
        if metric.ceiling is not None and rate is not None and rate > metric.ceiling
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
            *counting_defect,
            _run_split_text("first runs", first_runs),
            _run_split_text("repeat runs", repeat_runs),
            _NO_BACKSTOP_FIELD,
        ],
    )


def _split_first_and_repeat(consults: list[streams.Row], ts_field: str) -> tuple[list, list]:
    """A session's first consult in the window is a first run; each later one is a repeat run.

    Only windowed rows are seen, so a session whose first consult predates the window start has its
    first in-window consult counted as a first run."""
    seen: set[str] = set()
    first, repeat = [], []
    for row in sorted(consults, key=lambda r: (streams.row_time(r, ts_field), str(r.file), r.line)):
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
    ts_field = streams.STREAM_TABLE[metric.instrument].ts_field
    aborts = [r for r in part.real if _is_aborted_checkpoint(r)]
    tripped = [
        (
            r.data["session_id"],
            streams.row_time(r, ts_field),
            session_classify.strip_ns(r.data["triggering_agent"]),
        )
        for r in part.real
        if r.data.get("source") == STOP_HOOK
        and r.data.get("aborted") is True
        and isinstance(r.data.get("triggering_agent"), str)
    ]
    deferred = found = 0
    for row in aborts:
        aborted_at = streams.row_time(row, ts_field)
        for lens in map(session_classify.strip_ns, _lens_list(row)):
            deferred += 1
            found += any(
                session == row.data["session_id"]
                and ts >= aborted_at
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


def abort_frequency(metric: Metric, ctx: ReportContext) -> ReportNote:
    """Share of abort-mode rows that aborted, per source; the sources are never summed.

    ``checkpoint`` rows are the model-run rounds. ``stop-hook`` rows are one per lens result and say
    whether that result alone trips the abort rule."""
    part = ctx.partition(metric.instrument)
    sources = (CHECKPOINT, STOP_HOOK)
    is_abort_mode = lambda row: (
        row.data.get("mode") == ABORT_MODE and row.data.get("source") in sources
    )
    rows = [row for row in part.real if is_abort_mode(row)]
    unverified = sum(map(is_abort_mode, part.unverified))
    lines = ["abort frequency (aborted over abort-mode rows, per source):"]
    data: dict = {"unverified": unverified}
    for source in sources:
        of_source = [row for row in rows if row.data["source"] == source]
        aborted = sum(row.data.get("aborted") is True for row in of_source)
        lines.append(
            f"  {source}: "
            + (formatting.rate_text(aborted, len(of_source)) if of_source else "no abort-mode rows")
        )
        data[source] = {"aborted": aborted, "total": len(of_source)}
    lines.append(f"  unverified: {unverified}")
    return ReportNote("abort-frequency", tuple(lines), data)


def _is_aborted_checkpoint(row: streams.Row) -> bool:
    return (
        row.data.get("source") == CHECKPOINT
        and row.data.get("mode") == ABORT_MODE
        and row.data.get("aborted") is True
    )


def missing_scope_marker_split(skip_metric: Metric, ctx: ReportContext) -> ReportNote:
    """Missing-scope-marker events split by whether the session ran a consult.

    The event carries no dispatch source, so this is a heuristic: a session with a real consult row is
    ``consult`` and one without is ``direct``. A session that ran a consult and also made a direct
    dispatch counts every one of its events as ``consult``."""
    consult_sessions = {
        row.data["session_id"]
        for row in ctx.partition(skip_metric.instrument).real
        if row.data.get("source") == CONSULT
    }
    rows = streams.rows_in_window(
        ctx.rows(streams.BOUNDARY_EVENTS),
        streams.BOUNDARY_EVENTS.ts_field,
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
