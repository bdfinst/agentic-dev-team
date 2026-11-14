"""Tiered-findings metrics: the share of rendered reports a reader expanded.

Each ``tiered-renders`` row is one render of one report; renders of the same
report share its ``report`` key, so a report counts once per session and counts
as expanded when any of its renders used ``--expand``. Read-only.

Stdlib-only.
"""

from __future__ import annotations

from . import formatting, streams
from .formatting import ReportContext, ReportLine
from .prereg import Metric

NOT_EXPANDED = "none"
EXPAND_VALUES = (NOT_EXPANDED, "one", "all")


def _expand(row: streams.Row) -> str:
    value = streams.row_field(row, "expand", str)
    if value not in EXPAND_VALUES:
        raise streams.InputError(
            row.file,
            row.line,
            f"row field 'expand' is not one of {', '.join(EXPAND_VALUES)}",
            streams.REPAIR_ROW,
        )
    return value


def expand_rate(metric: Metric, ctx: ReportContext) -> ReportLine:
    """Expanded reports over rendered reports, one report per (session, report key)."""
    part = ctx.partition(metric.instrument)
    expanded: dict[tuple[str, str], bool] = {}
    for row in part.real:
        key = (row.data["session_id"], streams.row_field(row, "report", str))
        expanded[key] = expanded.get(key, False) or _expand(row) != NOT_EXPANDED
    return formatting.rate_line(
        metric,
        sum(expanded.values()),
        len(expanded),
        (session for session, _ in expanded),
        len(part.unverified),
    )
