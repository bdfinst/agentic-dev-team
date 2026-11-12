"""Report scaffolding shared by the metric modules: the per-run context, the
per-metric line record, and the number, rate and threshold text.

Every metric function returns a ``ReportLine``; the CLI renders them, so a
status token, a rate, an N or a truncated id is formatted in one place. The
metric modules never print. Read-only: nothing here writes a file.

Stdlib-only.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from . import prereg, streams

if TYPE_CHECKING:
    from .metrics_hooks import SubagentTranscripts

UNVERIFIED_LABEL = "UNVERIFIED (no session ids)"
#: Tokens that carry no value: the number is absent or untrustworthy. ``NULL (N=n)`` and
#: ``unmeasurable`` carry none either and are checked on their own.
_VALUELESS_TOKENS = (
    streams.TOKEN_NO_ROWS,
    streams.TOKEN_INSUFFICIENT,
    streams.TOKEN_NOT_ENTERED,
)


def percent(numerator: float, denominator: float) -> float | None:
    """``None`` when the denominator is zero, so a rate is never printed as 0% over nothing."""
    return None if denominator == 0 else 100.0 * numerator / denominator


def number_text(value: float) -> str:
    """Integral values print without a fraction: ``400`` not ``400.00``."""
    return str(int(value)) if float(value).is_integer() else f"{value:.2f}"


def rate_text(numerator: float, denominator: float) -> str:
    """``25.00% (3/12)``."""
    return f"{percent(numerator, denominator):.2f}% ({number_text(numerator)}/{number_text(denominator)})"


def threshold_text(threshold: streams.Threshold) -> str:
    return f"{threshold.op} {number_text(threshold.limit)}"


def bound_text(threshold: streams.Threshold) -> str:
    """The keep threshold as a ceiling (value must stay under it) or a floor (value must reach it)."""
    word = "ceiling" if threshold.op in ("<", "<=") else "floor"
    return f"{word} {number_text(threshold.limit)}"


def utc_now() -> str:
    """The current UTC time as ``YYYY-MM-DDTHH:MM:SSZ``."""
    # timezone.utc, not datetime.UTC: the latter needs Python 3.11 and the floor is 3.10.
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: UP017


def short_ids(session_ids: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({streams.truncate_id(s) for s in session_ids}))


@dataclass(frozen=True)
class ReportLine:
    """One metric on the report. ``headline`` is the value text printed only when
    the outcome carries a value; ``result`` holds the machine-readable numbers."""

    result: streams.MetricResult
    outcome: streams.Outcome
    n_unit: str = ""
    headline: str = ""
    threshold: streams.Threshold | None = None
    details: tuple[str, ...] = ()
    #: Detail lines that would reveal the value, printed only when the outcome carries one.
    value_details: tuple[str, ...] = ()
    unverified_rows: int | None = None
    #: Set from the metric's pre-registered identity class, in one place (``mark_id_less``).
    id_less: bool = False
    label: str = ""

    @property
    def verdict_input(self) -> bool:
        """An id-less or directional line prints its status but never feeds a verdict or the exit code."""
        return not self.id_less and not self.result.directional

    @property
    def carries_value(self) -> bool:
        token = self.outcome.token
        return (
            token not in _VALUELESS_TOKENS
            and not token.startswith(streams.TOKEN_NULL_PREFIX)
            and token != streams.UNMEASURABLE
        )

    def text(self) -> list[str]:
        parts = [f"{self.result.metric_id}:"]
        has_number = self.outcome.token != streams.UNMEASURABLE
        if self.id_less and has_number:
            parts.append(UNVERIFIED_LABEL)
        if self.label:
            parts.append(self.label)
        if self.carries_value:
            parts.append(self.headline)
            parts.append(f"| N={self.result.n} {self.n_unit}".rstrip())
            if self.threshold is not None:
                parts.append(f"| {bound_text(self.threshold)}")
            parts.append(f"| {self.outcome.token}")
        else:
            parts.append(self.outcome.token)
        if not self.verdict_input and has_number:
            parts.append("(excluded from verdict inputs)")
        lines = [" ".join(p for p in parts if p)]
        shown = self.details + (self.value_details if self.carries_value else ())
        lines += [f"  {detail}" for detail in shown]
        if self.result.sessions:
            lines.append(f"  sessions: {', '.join(self.result.sessions)}")
        if self.unverified_rows is not None:
            lines.append(f"  unverified: {self.unverified_rows}")
        return lines

    def as_dict(self) -> dict:
        record = {
            "metric_id": self.result.metric_id,
            "value": self.result.value if self.carries_value else None,
            "n": self.result.n,
            "sessions": list(self.result.sessions),
            "instrument": self.result.instrument,
            "directional": self.result.directional,
            "notes": self.result.notes,
            "status": self.outcome.token,
            "exit_code": self.outcome.exit_code,
            "verdict_input": self.verdict_input,
            "unverified_rows": self.unverified_rows,
            "details": list(self.details + (self.value_details if self.carries_value else ())),
        }
        if self.label:
            record["label"] = self.label
        return record


@dataclass(frozen=True)
class ReportNote:
    """An informational block that is not a pre-registered metric."""

    key: str
    lines: tuple[str, ...]
    data: dict


def measured_line(
    metric: prereg.Metric,
    value: float | None,
    n: int,
    sessions: Iterable[str],
    unverified: int,
    headline: str,
    details: Iterable[str] = (),
    value_details: Iterable[str] = (),
) -> ReportLine:
    """A metric measured over id-bearing rows, judged against its keep threshold at its own N."""
    return ReportLine(
        streams.MetricResult(
            metric.id, value, n, short_ids(sessions), metric.instrument, False
        ),
        streams.evaluate_status(n, metric.minimum_n, value, metric.keep),
        n_unit=metric.n_unit,
        headline=headline if n else "",
        threshold=metric.keep,
        details=tuple(details),
        value_details=tuple(value_details),
        unverified_rows=unverified,
    )


def rate_line(
    metric: prereg.Metric,
    numerator: float,
    denominator: float,
    sessions: Iterable[str],
    unverified: int,
    details: Iterable[str] = (),
    prefix: str = "",
    value_details: Iterable[str] = (),
) -> ReportLine:
    """A percent metric whose N is its denominator."""
    headline = (
        f"{prefix}{rate_text(numerator, denominator)}" if denominator else ""
    )
    return measured_line(
        metric,
        percent(numerator, denominator),
        int(denominator),
        sessions,
        unverified,
        headline,
        details,
        value_details,
    )


def mark_id_less(line: ReportLine, metric: prereg.Metric) -> ReportLine:
    """The one place a line learns it is id-less: from the metric's pre-registered identity class."""
    return replace(line, id_less=metric.identity_class == streams.ID_LESS)


def combined_exit_code(lines: Iterable[ReportLine]) -> int:
    """Exit code of the lines that feed a verdict; id-less and directional lines add none.

    Finding beats insufficient data: a breach is actionable even when another metric is short of rows."""
    codes = {line.outcome.exit_code for line in lines if line.verdict_input}
    if streams.EXIT_FINDING in codes:
        return streams.EXIT_FINDING
    if streams.EXIT_INSUFFICIENT in codes:
        return streams.EXIT_INSUFFICIENT
    return streams.EXIT_OK


@dataclass
class ReportContext:
    """Everything a metric function reads, resolved once per run."""

    sources: streams.Sources
    index: streams.SessionIndex
    #: The subagent transcripts of each session; the metrics that need an agent id read them here.
    transcripts: SubagentTranscripts
    start: datetime | None = None
    end: datetime | None = None
    boundary: datetime | None = None
    seed: int = 0
    manual: dict = field(default_factory=dict)
    manual_file: Path | None = None
    _rows: dict = field(default_factory=dict)
    _partitions: dict = field(default_factory=dict)

    def rows(self, spec: streams.StreamSpec) -> list[streams.Row]:
        """Every row of a stream, windowed or not; each file is read once per run."""
        if spec.name not in self._rows:
            self._rows[spec.name] = streams.load_rows(spec, self.sources)
        return self._rows[spec.name]

    def partition(self, stream_name: str) -> streams.Partition:
        """The in-window rows of a stream split into real and unverified; read once per run."""
        if stream_name not in self._partitions:
            spec = streams.STREAM_TABLE[stream_name]
            rows = streams.rows_in_window(
                self.rows(spec), spec.ts_field, self.start, self.end
            )
            self._partitions[stream_name] = streams.partition_rows(rows, self.index)
        return self._partitions[stream_name]
