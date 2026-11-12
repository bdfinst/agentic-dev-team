"""Subagent-hook metrics: skill-injection overhead and uptake, and the
completion-guard divergence rate with its hand-check sample.

Uptake and the sample's agent ids come from the subagent transcripts that
``session_log`` discovers, because neither stream carries an agent id; the
join grain is (session, agent type). Read-only.

Stdlib-only.
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from session_log import classify as session_classify
from session_log import signals as session_signals

from . import formatting, streams
from .formatting import ReportContext, ReportLine, ReportNote
from .prereg import Metric

FLAGGED = ("empty-final-turn", "truncated-final-turn")
CLEAN = "clean"
SAMPLE_SIZE = 20
_AGENT_PREFIX = "agent-"
_REPAIR = "repair or remove that row; the evaluation never edits the file"


@dataclass
class SubagentRun:
    """One dispatched agent's own transcript."""

    agent_id: str
    path: Path
    agent_type: str | None = None
    skills: frozenset[str] = frozenset()
    last_ts: datetime | None = None


@dataclass
class SubagentTranscripts:
    """Subagent transcripts of each session, found through ``session_log`` discovery."""

    projects_root: Path
    _mains: dict[str, Path] = field(default_factory=dict)
    _runs: dict[str, list[Path]] = field(default_factory=dict)
    _loaded: bool = False
    _read: dict[Path, SubagentRun] = field(default_factory=dict)

    def _discover(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.projects_root.is_dir():
            return
        for path in streams.session_discovery.all_transcripts(self.projects_root):
            parts = streams.session_discovery.relative_parts(self.projects_root, path)
            if streams.session_discovery.is_subagent_transcript(self.projects_root, path):
                self._runs.setdefault(parts[1], []).append(path)
            else:
                self._mains.setdefault(path.stem, path)

    def runs(self, session_id: str) -> list[SubagentRun]:
        self._discover()
        return [self._read_run(session_id, path) for path in self._runs.get(session_id, [])]

    def _read_run(self, session_id: str, path: Path) -> SubagentRun:
        if path not in self._read:
            run = SubagentRun(path.stem.removeprefix(_AGENT_PREFIX), path)
            attribution, skills = None, Counter()
            for record in streams.session_records.iter_file_records(path):
                if not isinstance(record, dict):
                    continue
                attribution = attribution or streams.session_records.attribution_agent_of(record)
                session_signals.accumulate_skill_agent_signals(
                    None, _content_of(record), skills, Counter(), {}
                )
                run.last_ts = _later(run.last_ts, record.get("timestamp"))
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
        main = self._mains.get(session_id)
        if main is None:
            return None
        dispatch_types: dict[str, str] = {}
        agent_types: dict[str, str] = {}
        for record in streams.session_records.iter_file_records(main):
            if isinstance(record, dict):
                streams.session_records.join_dispatch_agent_ids(record, dispatch_types, agent_types)
        found = agent_types.get(agent_id)
        return session_classify.strip_ns(found) if found else None


def _content_of(record: dict):
    message = record.get("message")
    return message.get("content") if isinstance(message, dict) else None


def _later(current: datetime | None, text) -> datetime | None:
    try:
        moment = streams.parse_utc(text)
    except ValueError:
        return current
    return moment if current is None or moment > current else current


def _row_field(row: streams.Row, name: str, kind: type):
    value = row.data.get(name)
    if isinstance(value, bool) or not isinstance(value, kind):
        raise streams.InputError(
            row.file, row.line, f"row field '{name}' is not a {kind.__name__}", _REPAIR
        )
    return value


def injection_overhead(metric: Metric, ctx: ReportContext) -> ReportLine:
    part = ctx.partition(metric.instrument)
    added = [_row_field(row, "added_chars", int) for row in part.real]
    value = sum(added) / len(added) if added else None
    return formatting.measured_line(
        metric,
        value,
        len(added),
        (r.data["session_id"] for r in part.real),
        len(part.unverified),
        f"mean {formatting.number_text(value)} {metric.unit}" if added else "",
    )


def injection_uptake(
    metric: Metric, ctx: ReportContext, transcripts: SubagentTranscripts
) -> ReportLine:
    """Share of injections whose injected skill the same session's subagent of that type loaded."""
    part = ctx.partition(metric.instrument)
    loaded_by_group: dict[tuple[str, str], set[str]] = {}
    hits = 0
    for row in part.real:
        session = row.data["session_id"]
        agent_type = session_classify.strip_ns(_row_field(row, "agent_type", str))
        injected = {
            session_classify.strip_ns(s)
            for s in _row_field(row, "skills", list)
            if isinstance(s, str)
        }
        key = (session, agent_type)
        if key not in loaded_by_group:
            loaded_by_group[key] = {
                skill
                for run in transcripts.runs(session)
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


def completion_guard_divergence(metric: Metric, ctx: ReportContext) -> ReportLine:
    part = ctx.partition(metric.instrument)
    counts = Counter(row.data.get("classification") for row in part.real)
    flagged = sum(counts[c] for c in FLAGGED)
    return formatting.rate_line(
        metric,
        flagged,
        flagged + counts[CLEAN],
        (r.data["session_id"] for r in part.real),
        len(part.unverified),
        details=[f"classified clean: {counts[CLEAN]}, flagged: {flagged}"],
    )


def completion_guard_sample(metric: Metric, ctx: ReportContext, transcripts: SubagentTranscripts) -> ReportNote:
    """A seeded sample of flagged stops for the hand-check, each with the transcript to open.

    The stop row names only a session, so each flagged stop is matched to the session's subagent
    transcript whose last record is nearest its time; each transcript matches one stop."""
    part = ctx.partition(metric.instrument)
    flagged = sorted(
        (r for r in part.real if r.data.get("classification") in FLAGGED),
        key=lambda r: (r.data["ts"], r.data["session_id"], str(r.file), r.line),
    )
    matched = _match_runs(flagged, transcripts)
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


def _match_runs(flagged: list[streams.Row], transcripts: SubagentTranscripts) -> dict:
    matched: dict = {}
    taken: set[Path] = set()
    for row in flagged:
        when = streams.parse_utc(row.data["ts"])
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
    """The transcript path under the projects root with the session directory cut to its 8-character
    prefix and a ``*``, so it works as a shell glob and never prints a full session id."""
    parts = streams.session_discovery.relative_parts(projects_root, path)
    short = streams.truncate_id(session_id)
    return "/".join(f"{short}*" if part == session_id else part for part in parts)
