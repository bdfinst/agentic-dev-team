"""Cost, tiering and skill-adoption metrics, and the hand-entered numbers.

``test-review`` token cost is read from the id-less cost stream, split at a
boundary timestamp; the line is directional and never feeds a verdict. The
verdict rate joins skill invocation counts (id-less) with tallies entered in
the manual-input file. Numbers no instrument persists print ``unmeasurable``.
Read-only: the manual-input file is never written.

Stdlib-only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from session_log import classify as session_classify

from . import formatting, streams
from .formatting import ReportContext, ReportLine, ReportNote
from .prereg import Metric

MANUAL_FILENAME = "benefit-manual-input.json"
TEST_REVIEW = "test-review"
VERDICT_SKILL = "source-verification"
#: Skills whose adoption the report checks: a skill invoked directly but never dispatched to is an orphan.
ADOPTION_SKILLS = (VERDICT_SKILL, "property-based-testing")
ORPHAN = "ORPHAN: wire-or-archive"
_REPAIR_ROW = "repair or remove that row; the evaluation never edits the file"
_REPAIR_MANUAL = "correct the entry; the evaluation never edits the file"


@dataclass(frozen=True)
class ManualEntry:
    value: float
    n: int
    sessions: tuple[str, ...]
    note: str


def manual_input_path(project_root: Path) -> Path:
    return project_root / ".claude" / "metrics" / MANUAL_FILENAME


def load_manual_input(path: Path, metric_ids: set[str]) -> dict[str, ManualEntry]:
    """Read the hand-entered numbers; an absent file means none entered, a malformed one is an input error."""
    text = streams.read_text(path)
    if text is None:
        return {}
    try:
        document = json.loads(text)
    except ValueError as exc:
        raise streams.InputError(
            path, getattr(exc, "lineno", 0) or 0, "file is not valid JSON", _REPAIR_MANUAL
        ) from exc
    if not isinstance(document, dict):
        raise streams.InputError(
            path, 0, "file is not a JSON object keyed by metric id", _REPAIR_MANUAL
        )
    lines = text.splitlines()
    entries = {}
    for key, raw in document.items():
        line = next((i for i, text_line in enumerate(lines, 1) if json.dumps(key) in text_line), 0)

        def fail(problem: str, action: str, line=line, key=key) -> streams.InputError:
            return streams.InputError(path, line, f"entry '{key}' {problem}", action)

        if key not in metric_ids:
            raise fail("has no pre-registered metric", "use a metric id from the pre-registration")
        entries[key] = _manual_entry(raw, fail)
    return entries


def _manual_entry(raw: object, fail) -> ManualEntry:
    if not isinstance(raw, dict):
        raise fail("is not an object", 'write {"value": <number>, "n": <integer>, "sessions": [...], "note": "..."}')
    value, n = raw.get("value"), raw.get("n")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise fail("value is not a number", "enter the measured value as a number")
    if isinstance(n, bool) or not isinstance(n, int) or n < 0:
        raise fail("n is not a non-negative integer", "enter how many items the value covers")
    sessions = raw.get("sessions", [])
    if not isinstance(sessions, list) or not all(isinstance(s, str) for s in sessions):
        raise fail("sessions is not a list of session ids", "list each session as a string")
    note = raw.get("note", "")
    if not isinstance(note, str):
        raise fail("note is not text", "write the note as a string")
    return ManualEntry(float(value), n, tuple(sessions), note)


def unmeasurable_line(metric: Metric, ctx: ReportContext) -> ReportLine:
    """A metric no instrument persists: no number, and the follow-up issue is the operator's."""
    return ReportLine(
        streams.MetricResult(metric.id, None, 0, (), metric.instrument, False, metric.computation),
        streams.Outcome(formatting.UNMEASURABLE, streams.EXIT_OK),
        details=(metric.computation,),
    )


def manual_metric(metric: Metric, ctx: ReportContext) -> ReportLine:
    """A number the operator entered by hand, judged like any other."""
    entry = ctx.manual.get(metric.id)
    n = entry.n if entry else 0
    value = entry.value if entry else None
    return ReportLine(
        streams.MetricResult(
            metric.id, value, n, formatting.short_ids(entry.sessions) if entry else (), metric.instrument, False, entry.note if entry else ""
        ),
        streams.evaluate_status(n, metric.minimum_n, value, metric.keep),
        n_unit=metric.n_unit,
        headline=f"{formatting.number_text(value)} {metric.unit}" if entry else "",
        threshold=metric.keep,
        details=("entered by hand in the manual-input file",) + ((f"note: {entry.note}",) if entry and entry.note else ()),
    )


def _is_test_review_cost_row(row: streams.Row) -> bool:
    buckets = row.data.get("by_agent_type")
    return isinstance(buckets, dict) and any(
        session_classify.strip_ns(name) == TEST_REVIEW for name in buckets
    )


def _test_review_tokens(row: streams.Row) -> int:
    total = 0
    for name, bucket in row.data["by_agent_type"].items():
        if session_classify.strip_ns(name) == TEST_REVIEW:
            if not isinstance(bucket, dict):
                raise streams.InputError(
                    row.file, row.line, f"row bucket '{name}' is not an object", _REPAIR_ROW
                )
            total += sum(
                streams.session_records.usage_field(bucket, field)
                for field in streams.session_records.USAGE_FIELDS
            )
    return total


def test_review_token_delta(metric: Metric, ctx: ReportContext) -> ReportLine:
    """Percent change in mean ``test-review`` tokens per cost row, after versus before the boundary.

    The rows carry no session id, so the line is directional and never a verdict input; the window
    bounds the after side only."""
    spec = streams.STREAM_TABLE[metric.instrument]
    rows = [r for r in streams.load_rows(spec, ctx.sources) if _is_test_review_cost_row(r)]
    before, after = streams.split_at_boundary(rows, spec.ts_field, ctx.boundary)
    after = streams.rows_in_window(after, spec.ts_field, ctx.start, ctx.end)
    means = [
        sum(map(_test_review_tokens, side)) / len(side) if side else None for side in (before, after)
    ]
    ns = (len(before), len(after))
    value = (
        100.0 * (means[1] - means[0]) / means[0] if None not in means and means[0] else None
    )
    if ns == (0, 0):
        outcome = streams.evaluate_status(0, metric.minimum_n, None, metric.keep)
    elif 0 in ns or value is None:
        outcome = streams.Outcome("insufficient", streams.EXIT_INSUFFICIENT)
    else:
        outcome = streams.evaluate_status(min(ns), metric.minimum_n, value, metric.keep)
    show_means = not outcome.token.startswith("NULL")
    sides = []
    for label, n, mean in zip(("before", "after"), ns, means):
        if n == 0:
            sides.append(f"{label}: N=0 insufficient")
        else:
            sides.append(
                f"{label}: N={n} {metric.n_unit}"
                + (f", mean {formatting.number_text(mean)} tokens" if show_means else "")
            )
    return ReportLine(
        streams.MetricResult(metric.id, value, min(ns), (), metric.instrument, True),
        outcome,
        n_unit=metric.n_unit,
        headline=f"delta {value:+.2f}%" if value is not None else "",
        threshold=metric.keep,
        details=(*sides, *(("delta: not computed",) if value is None else ())),
        verdict_input=False,
        label=f"DIRECTIONAL (confounds: {'; '.join(metric.confounds)})",
    )


def verdict_rate(metric: Metric, ctx: ReportContext) -> ReportLine:
    """``contradicted`` verdicts per skill invocation, from the id-less usage counts and the hand-entered tally."""
    spec = streams.STREAM_TABLE[metric.instrument]
    invocations = _invocations(streams.load_rows(spec, ctx.sources), VERDICT_SKILL)
    tally = ctx.manual.get(metric.id)
    value = tally.value / invocations if tally and invocations else None
    outcome = streams.evaluate_status(
        invocations, metric.minimum_n, value, metric.keep, side_empty=tally is None
    )
    details = [f"invocations: {invocations} (cumulative counts, not windowed)"]
    details.append(
        f"contradicted verdicts entered: {formatting.number_text(tally.value)} of {tally.n} verdicts"
        if tally
        else "contradicted tally: not entered in the manual-input file"
    )
    return ReportLine(
        streams.MetricResult(metric.id, value, invocations, (), metric.instrument, False),
        outcome,
        n_unit=metric.n_unit,
        headline=f"{value:.2f} per invocation" if value is not None else "",
        threshold=metric.keep,
        details=tuple(details),
        verdict_input=False,
    )


def _invocations(rows: list[streams.Row], skill: str) -> int:
    total = 0
    for row in rows:
        if session_classify.strip_ns(row.data["name"]) == skill:
            count = row.data.get("use_count", 0)
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise streams.InputError(
                    row.file, row.line, f"'{row.data['name']}' use_count is not a non-negative integer", _REPAIR_ROW
                )
            total += count
    return total


def skill_adoption(ctx: ReportContext, skills: tuple[str, ...] = ADOPTION_SKILLS) -> ReportNote:
    """Direct invocations beside consumer dispatches; a skill nothing dispatches to is an orphan.

    Direct counts come from the id-less usage file, so the block is unverified. Consumer dispatches are
    real injection rows that list the skill."""
    usage_spec = streams.STREAM_TABLE[ctx.stream_of("contradicted-rate")]
    usage_rows = streams.load_rows(usage_spec, ctx.sources)
    injections = ctx.partition(ctx.stream_of("injection-overhead")).real
    lines = [f"skill adoption: {formatting.UNVERIFIED_LABEL} (excluded from verdict inputs)"]
    data = {}
    for skill in skills:
        direct = _invocations(usage_rows, skill)
        consumer = sum(
            skill in {session_classify.strip_ns(s) for s in row.data.get("skills", []) if isinstance(s, str)}
            for row in injections
        )
        orphan = consumer == 0
        lines.append(
            f"  {skill}: direct invocations {direct}, consumer dispatches {consumer}" + (f" {ORPHAN}" if orphan else "")
        )
        data[skill] = {"direct": direct, "consumer": consumer, "orphan": orphan}
    return ReportNote("skill-adoption", tuple(lines), data)
