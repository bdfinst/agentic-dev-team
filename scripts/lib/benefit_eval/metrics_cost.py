"""Skill-adoption metrics and the hand-entered numbers.

The verdict rate joins skill invocation counts (id-less) with tallies entered in
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
VERDICT_SKILL = "source-verification"
#: Skills whose adoption the report checks: a skill invoked directly but never dispatched to is an orphan.
ADOPTION_SKILLS = (VERDICT_SKILL, "property-based-testing")
ORPHAN = "ORPHAN: wire-or-archive"
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

        def input_error(problem: str, action: str, line=line, key=key) -> streams.InputError:
            return streams.InputError(path, line, f"entry '{key}' {problem}", action)

        if key not in metric_ids:
            raise input_error("has no pre-registered metric", "use a metric id from the pre-registration")
        entries[key] = _manual_entry(raw, input_error)
    return entries


def _manual_entry(raw: object, input_error) -> ManualEntry:
    if not isinstance(raw, dict):
        raise input_error("is not an object", 'write {"value": <number>, "n": <integer>, "sessions": [...], "note": "..."}')
    value, n = raw.get("value"), raw.get("n")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise input_error("value is not a number", "enter the measured value as a number")
    if isinstance(n, bool) or not isinstance(n, int) or n < 0:
        raise input_error("n is not a non-negative integer", "enter how many items the value covers")
    sessions = raw.get("sessions", [])
    if not isinstance(sessions, list) or not all(isinstance(s, str) for s in sessions):
        raise input_error("sessions is not a list of session ids", "list each session as a string")
    note = raw.get("note", "")
    if not isinstance(note, str):
        raise input_error("note is not text", "write the note as a string")
    return ManualEntry(float(value), n, tuple(sessions), note)


def unmeasurable_line(metric: Metric, ctx: ReportContext) -> ReportLine:
    """A metric no instrument persists: no number, and the follow-up issue is the operator's."""
    return ReportLine(
        streams.MetricResult(metric.id, None, 0, (), metric.instrument, False, metric.computation),
        streams.Outcome(streams.UNMEASURABLE, streams.EXIT_OK),
        details=(metric.computation,),
    )


def manual_metric(metric: Metric, ctx: ReportContext) -> ReportLine:
    """A number the operator entered by hand, judged like any other.

    Session ids the operator lists are checked against the transcripts; an id with no real transcript is
    counted as unverified and left off the printed list."""
    entry = ctx.manual.get(metric.id)
    n = entry.n if entry else 0
    value = entry.value if entry else None
    real = [s for s in (entry.sessions if entry else ()) if ctx.index.classify(s) == streams.SESSION_REAL]
    return ReportLine(
        streams.MetricResult(
            metric.id, value, n, formatting.short_ids(real), metric.instrument, False, entry.note if entry else ""
        ),
        streams.evaluate_status(n, metric.minimum_n, value, metric.keep),
        n_unit=metric.n_unit,
        headline=f"{formatting.number_text(value)} {metric.unit}" if entry else "",
        threshold=metric.keep,
        details=("entered by hand in the manual-input file",) + ((f"note: {entry.note}",) if entry and entry.note else ()),
        unverified_rows=len(entry.sessions) - len(real) if entry else None,
    )


def verdict_rate(metric: Metric, ctx: ReportContext) -> ReportLine:
    """``contradicted`` verdicts per skill invocation, from the id-less usage counts and the hand-entered tally."""
    spec = streams.STREAM_TABLE[metric.instrument]
    invocations = _invocations(ctx.rows(spec), VERDICT_SKILL)
    tally = ctx.manual.get(metric.id)
    value = tally.value / invocations if tally and invocations else None
    outcome = streams.evaluate_status(
        invocations, metric.minimum_n, value, metric.keep, side_empty=tally is None
    )
    if tally is None and outcome.token == streams.TOKEN_INSUFFICIENT:
        outcome = streams.Outcome(streams.TOKEN_NOT_ENTERED, outcome.exit_code)
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
    )


def _invocations(rows: list[streams.Row], skill: str) -> int:
    total = 0
    for row in rows:
        if session_classify.strip_ns(row.data["name"]) == skill and "use_count" in row.data:
            total += streams.row_field(
                row, "use_count", int, minimum=0, label=f"'{row.data['name']}' use_count"
            )
    return total


def skill_adoption(
    metric: Metric, ctx: ReportContext, skills: tuple[str, ...] = ADOPTION_SKILLS
) -> ReportNote:
    """Direct invocations beside consumer dispatches; a skill nothing dispatches to is an orphan.
    The block covers the fixed adoption skills, so ``metric`` is accepted only to match every other note.

    Direct counts come from the id-less usage file, so the block is unverified. Consumer dispatches are
    real injection rows that list the skill."""
    usage_rows = ctx.rows(streams.STREAM_TABLE[streams.STREAM_ARTIFACT_USAGE])
    injections = ctx.partition(streams.STREAM_SKILL_INJECTION).real
    lines = [f"skill adoption: {formatting.UNVERIFIED_LABEL} (excluded from verdict inputs)"]
    data = {}
    for skill in skills:
        direct = _invocations(usage_rows, skill)
        consumer = sum(
            skill in {session_classify.strip_ns(s) for s in streams.injected_skills(row)}
            for row in injections
        )
        orphan = consumer == 0
        lines.append(
            f"  {skill}: direct invocations {direct}, consumer dispatches {consumer}" + (f" {ORPHAN}" if orphan else "")
        )
        data[skill] = {"direct": direct, "consumer": consumer, "orphan": orphan}
    return ReportNote("skill-adoption", tuple(lines), data)
