"""Subagent-hook metrics: skill-injection overhead and uptake, the
completion-guard divergence rate with its hand-check sample, the
``test-review`` dispatch token change, and the tiered-findings report-size cut.

Uptake, the sample's agent ids and the dispatch tokens come from the subagent
transcripts that ``session_log`` discovers, because the streams carry no agent
id; the join grain is (session, agent type). Read-only.

Stdlib-only.
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from session_log import classify as session_classify
from session_log import discovery as session_discovery
from session_log import records as session_records
from session_log import signals as session_signals

from . import formatting, streams
from .formatting import ReportContext, ReportLine, ReportNote
from .prereg import Metric

FLAGGED = ("empty-final-turn", "truncated-final-turn")
CLEAN = "clean"
SAMPLE_SIZE = 20
TEST_REVIEW = "test-review"
_AGENT_PREFIX = "agent-"


@dataclass
class SubagentRun:
    """One dispatched agent's own transcript."""

    agent_id: str
    path: Path
    agent_type: str | None = None
    skills: frozenset[str] = frozenset()
    last_ts: datetime | None = None
    #: Every token field of every usage record in the transcript, summed.
    tokens: int | float = 0


@dataclass
class SubagentTranscripts:
    """The subagent transcripts of each session, found through the shared ``SessionIndex``."""

    index: streams.SessionIndex
    _read: dict[Path, SubagentRun] = field(default_factory=dict)

    def runs(self, session_id: str) -> list[SubagentRun]:
        return [
            self._read_run(session_id, path)
            for path in self.index.subagent_transcripts(session_id)
        ]

    def _read_run(self, session_id: str, path: Path) -> SubagentRun:
        if path not in self._read:
            run = SubagentRun(path.stem.removeprefix(_AGENT_PREFIX), path)
            attribution, skills = None, Counter()
            for record in session_records.iter_file_records(path):
                if not isinstance(record, dict):
                    continue
                attribution = attribution or session_records.attribution_agent_of(record)
                session_signals.accumulate_skill_agent_signals(
                    None, _content_of(record), skills, Counter(), {}
                )
                run.last_ts = _later(run.last_ts, record.get("timestamp"))
                usage = session_records.usage_of(record)
                if usage is not None:
                    run.tokens += _token_total(usage)
            run.skills = frozenset(skills)
            run.agent_type = (
                session_classify.strip_ns(attribution)
                if attribution
                else self._dispatched_type(session_id, run.agent_id)
            )
            self._read[path] = run
        return self._read[path]

    def _dispatched_type(self, session_id: str, agent_id: str) -> str | None:
        """The agent type the main transcript recorded when it dispatched ``agent_id``."""
        main = self.index.main_transcript(session_id)
        if main is None:
            return None
        dispatch_types: dict[str, str] = {}
        agent_types: dict[str, str] = {}
        for record in session_records.iter_file_records(main):
            if isinstance(record, dict):
                session_records.join_dispatch_agent_ids(record, dispatch_types, agent_types)
        found = agent_types.get(agent_id)
        return session_classify.strip_ns(found) if found else None


def _content_of(record: dict):
    message = record.get("message")
    return message.get("content") if isinstance(message, dict) else None


def _token_total(usage: dict) -> int | float:
    """Sum of the usage token fields; a non-numeric value in a transcript adds nothing."""
    values = (session_records.usage_field(usage, f) for f in session_records.USAGE_FIELDS)
    return sum(v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool))


def _later(current: datetime | None, text) -> datetime | None:
    try:
        moment = streams.parse_utc(text)
    except ValueError:
        return current
    return moment if current is None or moment > current else current


def injection_overhead(metric: Metric, ctx: ReportContext) -> ReportLine:
    part = ctx.partition(metric.instrument)
    added = [streams.row_field(row, "added_chars", int) for row in part.real]
    value = sum(added) / len(added) if added else None
    return formatting.measured_line(
        metric,
        value,
        len(added),
        (r.data["session_id"] for r in part.real),
        len(part.unverified),
        f"mean {formatting.number_text(value)} {metric.unit}" if added else "",
    )


def injection_uptake(metric: Metric, ctx: ReportContext) -> ReportLine:
    """Share of injections whose injected skill the same session's subagent of that type loaded."""
    part = ctx.partition(metric.instrument)
    loaded_by_group: dict[tuple[str, str], set[str]] = {}
    hits = 0
    for row in part.real:
        session = row.data["session_id"]
        agent_type = session_classify.strip_ns(streams.row_field(row, "agent_type", str))
        injected = {session_classify.strip_ns(s) for s in streams.injected_skills(row)}
        key = (session, agent_type)
        if key not in loaded_by_group:
            loaded_by_group[key] = {
                skill
                for run in ctx.transcripts.runs(session)
                if run.agent_type == agent_type
                for skill in run.skills
            }
        hits += bool(injected & loaded_by_group[key])
    return formatting.rate_line(
        metric,
        hits,
        len(part.real),
        (r.data["session_id"] for r in part.real),
        len(part.unverified),
        prefix="uptake ",
    )


def report_size_cut(metric: Metric, ctx: ReportContext) -> ReportLine:
    """Mean per-round percent by which the Tier-1 report is smaller than the untiered one.

    A clean-pass round renders the same summary either way, so it is counted and left out."""
    part = ctx.partition(metric.instrument)
    cuts, sessions, clean = [], [], 0
    for row in part.real:
        full = streams.row_field(row, "full_bytes", int, minimum=0)
        tiered = streams.row_field(row, "tiered_bytes", int, minimum=0)
        if streams.row_field(row, "findings", int, minimum=0) == 0 or full == 0:
            clean += 1
            continue
        cuts.append(formatting.percent(full - tiered, full))
        sessions.append(row.data["session_id"])
    value = sum(cuts) / len(cuts) if cuts else None
    return formatting.measured_line(
        metric,
        value,
        len(cuts),
        sessions,
        len(part.unverified),
        f"mean {formatting.number_text(value)} {metric.unit}" if cuts else "",
        details=[f"clean-pass rounds left out: {clean}"],
    )


def completion_guard_divergence(metric: Metric, ctx: ReportContext) -> ReportLine:
    part = ctx.partition(metric.instrument)
    counts = Counter(_classification(row) for row in part.real)
    flagged = sum(counts[c] for c in FLAGGED)
    return formatting.rate_line(
        metric,
        flagged,
        flagged + counts[CLEAN],
        (r.data["session_id"] for r in part.real),
        len(part.unverified),
        value_details=[f"classified clean: {counts[CLEAN]}, flagged: {flagged}"],
    )


def completion_guard_sample(metric: Metric, ctx: ReportContext) -> ReportNote:
    """A seeded sample of flagged stops for the hand-check, each with the transcript to open.

    The stop row names only a session, so each flagged stop is matched to the session's subagent
    transcript whose last record is nearest its time; each transcript matches one stop."""
    part = ctx.partition(metric.instrument)
    ts_field = streams.STREAM_TABLE[metric.instrument].ts_field
    flagged = sorted(
        (r for r in part.real if _classification(r) in FLAGGED),
        key=lambda r: (streams.row_time(r, ts_field), r.data["session_id"], str(r.file), r.line),
    )
    matched = _match_runs(flagged, ts_field, ctx.transcripts)
    chosen = random.Random(ctx.seed).sample(flagged, min(SAMPLE_SIZE, len(flagged)))
    lines = [f"{metric.id} hand-check sample (seed {ctx.seed}): {len(chosen)} of {len(flagged)} flagged"]
    data = []
    for row in chosen:
        run = matched.get((row.file, row.line))
        agent = run.agent_id if run else "unmatched"
        where = _glob_path(ctx.sources.projects_root, run.path, row.data["session_id"]) if run else "none"
        session = streams.truncate_id(row.data["session_id"])
        lines.append(f"  session={session} classification={row.data['classification']} agent={agent} transcript={where}")
        data.append(
            {"session": session, "classification": row.data["classification"], "agent": agent, "transcript": where}
        )
    return ReportNote("completion-guard-sample", tuple(lines), {"seed": ctx.seed, "sample": data})


def _classification(row: streams.Row) -> str:
    return streams.row_field(row, "classification", str)


def _match_runs(flagged: list[streams.Row], ts_field: str, transcripts: SubagentTranscripts) -> dict:
    matched: dict = {}
    taken: set[Path] = set()
    for row in flagged:
        when = streams.row_time(row, ts_field)
        free = [
            run
            for run in transcripts.runs(row.data["session_id"])
            if run.path not in taken and run.last_ts is not None
        ]
        if free:
            run = min(free, key=lambda r: (abs((r.last_ts - when).total_seconds()), str(r.path)))
            taken.add(run.path)
            matched[(row.file, row.line)] = run
    return matched


def _glob_path(projects_root: Path, path: Path, session_id: str) -> str:
    """The transcript as a shell glob: ``*`` for the project directory (its encoded name holds the
    user name and checkout path), the session directory cut to its 8-character prefix and a ``*``,
    then the subagent file. It never prints a full session id."""
    parts = session_discovery.relative_parts(projects_root, path)
    return "/".join(("*", f"{streams.truncate_id(session_id)}*", *parts[2:]))


def test_review_token_delta(metric: Metric, ctx: ReportContext) -> ReportLine:
    """Percent change in mean tokens per ``test-review`` dispatch, after versus before the boundary.

    A dispatch is one subagent transcript of a real session whose agent type is ``test-review``; its
    tokens are the sum of its usage records and it sits at its last record time. The window bounds the
    after side only. The line is directional: it never feeds a verdict. Raises ``InputError`` when the
    run has no boundary, because the split needs one."""
    if ctx.boundary is None:
        raise streams.InputError(
            "--boundary",
            0,
            f"{metric.id} splits before and after a boundary and none was given",
            "pass --boundary as ISO 8601 UTC ending in Z, for example 2026-11-12T10:00:00Z",
        )
    dispatches: list[tuple[str, SubagentRun]] = []
    left_out = 0
    for session in ctx.index.sessions_with_subagents():
        runs = [run for run in ctx.transcripts.runs(session) if run.agent_type == TEST_REVIEW]
        if ctx.index.classify(session) == streams.SESSION_REAL:
            dispatches += [(session, run) for run in runs]
        else:
            left_out += len(runs)
    timed = [(session, run) for session, run in dispatches if run.last_ts is not None]
    before = [(s, r) for s, r in timed if r.last_ts < ctx.boundary]
    after = [
        (s, r) for s, r in timed
        if r.last_ts >= ctx.boundary and streams.in_window(r.last_ts, ctx.start, ctx.end)
    ]
    means = [
        sum(run.tokens for _, run in side) / len(side) if side else None for side in (before, after)
    ]
    ns = (len(before), len(after))
    value = 100.0 * (means[1] - means[0]) / means[0] if None not in means and means[0] else None
    # One empty side leaves the other side's N to decide between NULL and insufficient.
    present = [n for n in ns if n]
    outcome = streams.evaluate_status(
        min(present, default=0), metric.minimum_n, value, metric.keep, side_empty=0 in ns
    )
    show_means = not outcome.token.startswith(streams.TOKEN_NULL_PREFIX)
    sides = []
    for label, n, mean in zip(("before", "after"), ns, means):
        if n == 0:
            sides.append(f"{label}: N=0 {streams.TOKEN_INSUFFICIENT}")
        else:
            sides.append(
                f"{label}: N={n} {metric.n_unit}"
                + (f", mean {formatting.number_text(mean)} tokens" if show_means else "")
            )
    notes = []
    if left_out:
        notes.append(f"left out: {left_out} dispatches of sessions with no real transcript")
    if len(timed) < len(dispatches):
        notes.append(f"left out: {len(dispatches) - len(timed)} dispatches with no timestamp")
    return ReportLine(
        streams.MetricResult(
            metric.id,
            value,
            min(present, default=0),
            formatting.short_ids(session for session, _ in (*before, *after)),
            metric.instrument,
            True,
        ),
        outcome,
        n_unit=metric.n_unit,
        headline=f"delta {value:+.2f}%" if value is not None else "",
        threshold=metric.keep,
        details=(*sides, *(("delta: not computed",) if value is None else ()), *notes),
        label=f"DIRECTIONAL (confounds: {'; '.join(metric.confounds)})",
    )
