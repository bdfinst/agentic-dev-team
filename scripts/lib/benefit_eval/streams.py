"""Shared reader, real-session filter, window helpers and instrument audit.

Every benefit-evaluation command reads instruments through this module, so a
stream name, an identity class, a timestamp rule or an exit code exists in one
place. Everything here is read-only: it opens files for reading and never
creates, rewrites or reorders one.

Stdlib-only. Stream names come from ``hooks/lib/instrument_log``; paths from
``hooks/lib/artifact_paths``; transcript discovery from ``scripts/lib/session_log``.
"""

from __future__ import annotations

import json
import operator
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parents[3] / "plugins" / "dev-team"
for _dir in (_PLUGIN_ROOT / "hooks" / "lib", _PLUGIN_ROOT / "scripts" / "lib"):
    if str(_dir) not in sys.path:
        sys.path.insert(0, str(_dir))

import artifact_paths
import instrument_log
from session_log import discovery as session_discovery
from session_log import records as session_records

EXIT_OK = 0
EXIT_FINDING = 1
EXIT_MALFORMED = 2
EXIT_INSUFFICIENT = 3

ID_BEARING = "id-bearing"
ID_LESS = "id-less"

#: Prereg instrument value for a number the operator enters by hand.
MANUAL_INSTRUMENT = "manual-input"
#: Prereg instrument value for a metric no stream can measure.
NO_INSTRUMENT = "none"

KIND_STREAM = "stream"
KIND_MANUAL = "manual"
KIND_NONE = "none"

#: Real sessions an id-bearing instrument must show before it counts as emitting.
MIN_REAL_SESSIONS = 3
#: Characters of a session id that may appear in output.
SESSION_ID_CHARS = 8

STATUS_CONFIRMED = "confirmed"
STATUS_GAP = "gap"
STATUS_NO_INSTRUMENT = "no instrument"
STATUS_NO_SESSION_IDS = "no session ids"
STATUS_MANUAL = "manual"
#: Statuses that make the audit exit 1.
_FINDING_STATUSES = frozenset({STATUS_GAP, STATUS_NO_INSTRUMENT})
#: Statuses for which the audit has row and session counts to print.
_COUNTED_STATUSES = frozenset({STATUS_CONFIRMED, STATUS_GAP, STATUS_NO_SESSION_IDS})

SESSION_REAL = "real"
SESSION_NO_TRANSCRIPT = "no transcript"
SESSION_UNPARSEABLE = "unparseable transcript"
SESSION_EMPTY = "empty transcript"


_REPAIR_LINE = "repair or remove that line; the evaluation never edits the file"
_REPAIR_FILE = "repair the file; the evaluation never edits it"
_REPAIR_ROW = "repair or remove that row; the evaluation never edits the file"
_CHECK_READ = "check the file permissions and encoding; the evaluation never edits it"


class InputError(Exception):
    """Malformed structured input. ``line`` is 0 for a file-level problem."""

    def __init__(self, file: Path | str, line: int, problem: str, action: str):
        self.file, self.line, self.problem, self.action = (
            str(file),
            line,
            problem,
            action,
        )
        super().__init__(self.message())

    def message(self) -> str:
        return f"{self.file}:{self.line}: {self.problem}. Next: {self.action}"


@dataclass(frozen=True)
class StreamSpec:
    name: str
    filename: str
    identity_class: str
    scope: str  # "project" (.claude/metrics under a project root) or "home"
    ts_field: str
    jsonl: bool


def _spec(
    name: str, identity: str, scope: str, ts_field: str, jsonl: bool = True
) -> StreamSpec:
    return StreamSpec(
        name, f"{name}.{'jsonl' if jsonl else 'json'}", identity, scope, ts_field, jsonl
    )


#: Every instrument the evaluation can read, with its identity class.
STREAM_TABLE: dict[str, StreamSpec] = {
    **{
        name: _spec(name, ID_BEARING, "project", "ts")
        for name in sorted(instrument_log.STREAMS)
    },
    "cost-metering": _spec("cost-metering", ID_LESS, "project", "timestamp"),
    "artifact-usage": _spec(
        "artifact-usage", ID_LESS, "home", "last_used_at", jsonl=False
    ),
}


@dataclass(frozen=True)
class Sources:
    """Where the evaluation reads from."""

    project_roots: tuple[Path, ...]
    home_metrics: Path
    projects_root: Path  # the ~/.claude/projects-shaped transcript tree


@dataclass(frozen=True)
class Row:
    file: Path
    line: int
    data: dict


def truncate_id(session_id: str) -> str:
    return session_id[:SESSION_ID_CHARS]


def _stream_files(spec: StreamSpec, sources: Sources) -> list[Path]:
    if spec.scope == "home":
        return [sources.home_metrics / spec.filename]
    return sorted({_project_stream_file(spec, root) for root in sources.project_roots}, key=str)


def _project_stream_file(spec: StreamSpec, root: Path) -> Path:
    """The ``.claude/metrics`` file, or the un-migrated legacy ``metrics`` file when only that exists.

    The audit never moves a file, so a project that has not migrated yet is read in place."""
    current = artifact_paths.resolve_file("metrics", spec.filename, root, migrate=False)
    legacy = artifact_paths.project_root(root) / "metrics" / spec.filename
    return legacy if not current.exists() and legacy.is_file() else current


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as exc:
        raise InputError(
            path,
            0,
            f"cannot read file ({type(exc).__name__})",
            _CHECK_READ,
        ) from exc


def _read_jsonl(path: Path) -> list[Row]:
    text = read_text(path)
    rows: list[Row] = []
    for number, line in enumerate((text or "").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except ValueError as exc:
            raise InputError(
                path,
                number,
                "line is not valid JSON",
                _REPAIR_LINE,
            ) from exc
        if not isinstance(data, dict):
            raise InputError(
                path,
                number,
                "line is not a JSON object",
                _REPAIR_LINE,
            )
        rows.append(Row(path, number, data))
    return rows


def _read_json_object(path: Path) -> list[Row]:
    """A single-object file becomes one row per top-level key."""
    text = read_text(path)
    if text is None:
        return []
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise InputError(
            path,
            getattr(exc, "lineno", 0) or 0,
            "file is not valid JSON",
            _REPAIR_FILE,
        ) from exc
    if not isinstance(data, dict):
        raise InputError(
            path,
            0,
            "file is not a JSON object",
            _REPAIR_FILE,
        )
    return [
        Row(path, 1, {"name": key, **(value if isinstance(value, dict) else {})})
        for key, value in data.items()
    ]


def load_rows(spec: StreamSpec, sources: Sources) -> list[Row]:
    """Every row of a stream across all its files; absent files add nothing."""
    read = _read_jsonl if spec.jsonl else _read_json_object
    return [row for path in _stream_files(spec, sources) for row in read(path)]


def _transcript_verdict(path: Path) -> str:
    """Parse the whole transcript: real needs one record and every non-blank line a JSON object."""
    records = objects = 0
    for record in session_records.iter_file_records(path):
        records += 1
        objects += isinstance(record, dict)
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            lines = sum(1 for line in handle if line.strip())
    except OSError:
        return SESSION_UNPARSEABLE
    if lines == 0:
        return SESSION_EMPTY
    return SESSION_REAL if records == objects == lines else SESSION_UNPARSEABLE


class SessionIndex:
    """Maps a session id to its main-thread transcript and says whether it parses."""

    def __init__(self, projects_root: Path):
        self._root = projects_root
        self._paths: dict[str, Path] | None = None
        self._verdicts: dict[str, str] = {}

    def _transcripts(self) -> dict[str, Path]:
        if self._paths is None:
            self._paths = {}
            if self._root.is_dir():
                for path in session_discovery.all_transcripts(self._root):
                    if not session_discovery.is_subagent_transcript(self._root, path):
                        self._paths.setdefault(path.stem, path)
        return self._paths

    def classify(self, session_id: str) -> str:
        if session_id not in self._verdicts:
            path = self._transcripts().get(session_id)
            self._verdicts[session_id] = (
                SESSION_NO_TRANSCRIPT if path is None else _transcript_verdict(path)
            )
        return self._verdicts[session_id]


@dataclass
class Partition:
    """Rows split by whether their session is real. Only ``real`` rows may feed a number."""

    real: list[Row] = field(default_factory=list)
    unverified: list[Row] = field(default_factory=list)
    skipped_sessions: set[str] = field(default_factory=set)

    @property
    def real_sessions(self) -> set[str]:
        return {row.data["session_id"] for row in self.real}


def partition_rows(rows: Iterable[Row], index: SessionIndex) -> Partition:
    part = Partition()
    for row in rows:
        session_id = row.data.get("session_id")
        verdict = (
            index.classify(session_id)
            if isinstance(session_id, str) and session_id
            else None
        )
        if verdict == SESSION_REAL:
            part.real.append(row)
            continue
        part.unverified.append(row)
        if verdict == SESSION_UNPARSEABLE:
            part.skipped_sessions.add(session_id)
    return part


_UTC_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")


def parse_utc(text: str) -> datetime:
    """Parse an ISO 8601 UTC timestamp that ends in ``Z``; raise ``ValueError`` otherwise."""
    if not isinstance(text, str) or not _UTC_Z.match(text):
        raise ValueError(f"not an ISO 8601 UTC timestamp ending in Z: {text!r}")
    # timezone.utc, not datetime.UTC: the latter needs Python 3.11 and the floor is 3.10.
    return datetime.fromisoformat(text[:-1]).replace(tzinfo=timezone.utc)  # noqa: UP017


def row_time(row: Row, ts_field: str) -> datetime:
    try:
        return parse_utc(row.data.get(ts_field))
    except ValueError as exc:
        raise InputError(
            row.file,
            row.line,
            f"row has no valid '{ts_field}' timestamp",
            _REPAIR_ROW,
        ) from exc


def rows_in_window(
    rows: Iterable[Row],
    ts_field: str,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[Row]:
    """Rows with ``start <= ts < end``; a missing bound is open."""
    kept = []
    for row in rows:
        when = row_time(row, ts_field)
        if (start is None or when >= start) and (end is None or when < end):
            kept.append(row)
    return kept


def split_at_boundary(
    rows: Iterable[Row], ts_field: str, boundary: datetime
) -> tuple[list[Row], list[Row]]:
    """``(before, after)``: before is ``ts < boundary``, after is ``ts >= boundary``."""
    before: list[Row] = []
    after: list[Row] = []
    for row in rows:
        (before if row_time(row, ts_field) < boundary else after).append(row)
    return before, after


#: The one table of threshold operators; everything else derives from it.
_OPERATOR_FUNCS = {
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
}
OPERATORS = tuple(_OPERATOR_FUNCS)
INCLUSIVITY = {op: "inclusive" if "=" in op else "exclusive" for op in OPERATORS}
OPERATOR_PATTERN = "|".join(map(re.escape, OPERATORS))


@dataclass(frozen=True)
class Threshold:
    op: str
    limit: float

    def holds(self, value: float) -> bool:
        """Whether ``value`` is on the within side of this threshold."""
        return _OPERATOR_FUNCS[self.op](value, self.limit)


@dataclass(frozen=True)
class Outcome:
    token: str
    exit_code: int


def evaluate_status(
    n: int,
    min_n: int,
    value: float | None,
    threshold: Threshold,
    side_empty: bool = False,
) -> Outcome:
    """Condition-to-token-to-exit mapping, first match wins.

    A missing ``value`` with enough rows means a side has nothing to compare, so it
    reads as ``insufficient``."""
    if n == 0:
        return Outcome("no rows in window", EXIT_INSUFFICIENT)
    if n < min_n:
        return Outcome(f"NULL (N={n})", EXIT_INSUFFICIENT)
    if side_empty or value is None:
        return Outcome("insufficient", EXIT_INSUFFICIENT)
    if threshold.holds(value):
        return Outcome("within", EXIT_OK)
    return Outcome("breach", EXIT_FINDING)


@dataclass(frozen=True)
class MetricResult:
    """One report metric. ``sessions`` holds truncated ids."""

    metric_id: str
    value: float | None
    n: int
    sessions: tuple[str, ...]
    instrument: str
    directional: bool
    notes: str = ""


@dataclass(frozen=True)
class InstrumentStatus:
    """One audited instrument. ``session_ids`` holds truncated ids."""

    instrument: str
    status: str
    metrics: tuple[str, ...]
    rows: int = 0
    real_sessions: int = 0
    session_ids: tuple[str, ...] = ()
    unverified_rows: int = 0
    skipped_transcripts: int = 0

    @property
    def is_finding(self) -> bool:
        return self.status in _FINDING_STATUSES

    @property
    def has_counts(self) -> bool:
        return self.status in _COUNTED_STATUSES


def classify_instrument(name: object) -> tuple[str, str]:
    """``(kind, identity_class)`` for a pre-registered instrument name.

    Kind is ``stream`` (a persisted stream), ``manual`` (operator input) or ``none``
    (nothing measures it). Raises ``TypeError`` for a non-string and ``ValueError``
    for an unknown name."""
    if not isinstance(name, str):
        raise TypeError(f"instrument must be a string, got {type(name).__name__}")
    if name == MANUAL_INSTRUMENT:
        return KIND_MANUAL, ID_BEARING
    if name == NO_INSTRUMENT:
        return KIND_NONE, ID_LESS
    if name in STREAM_TABLE:
        return KIND_STREAM, STREAM_TABLE[name].identity_class
    known = ", ".join([*STREAM_TABLE, MANUAL_INSTRUMENT, NO_INSTRUMENT])
    raise ValueError(f"unknown instrument '{name}'; use one of: {known}")


def audit(metrics: Iterable, sources: Sources) -> list[InstrumentStatus]:
    """Audit each distinct instrument the pre-registered ``metrics`` name.

    ``metrics`` are objects with ``id`` and ``instrument`` attributes."""
    by_instrument: dict[str, list[str]] = {}
    for metric in metrics:
        by_instrument.setdefault(metric.instrument, []).append(metric.id)
    index = SessionIndex(sources.projects_root)
    return [
        _audit_instrument(name, tuple(ids), sources, index)
        for name, ids in sorted(by_instrument.items())
    ]


def audit_exit_code(statuses: Iterable[InstrumentStatus]) -> int:
    return (
        EXIT_FINDING if any(s.is_finding for s in statuses) else EXIT_OK
    )


def _audit_instrument(
    name: str, ids: tuple[str, ...], sources: Sources, index: SessionIndex
) -> InstrumentStatus:
    kind, _ = classify_instrument(name)
    if kind == KIND_MANUAL:
        return InstrumentStatus(name, STATUS_MANUAL, ids)
    if kind == KIND_NONE:
        return InstrumentStatus(name, STATUS_NO_INSTRUMENT, ids)
    spec = STREAM_TABLE[name]
    rows = load_rows(spec, sources)
    if not rows:
        return InstrumentStatus(name, STATUS_GAP, ids)
    if spec.identity_class == ID_LESS:
        return InstrumentStatus(name, STATUS_NO_SESSION_IDS, ids, rows=len(rows))
    part = partition_rows(rows, index)
    sessions = part.real_sessions
    return InstrumentStatus(
        name,
        STATUS_CONFIRMED if len(sessions) >= MIN_REAL_SESSIONS else STATUS_GAP,
        ids,
        rows=len(rows),
        real_sessions=len(sessions),
        session_ids=tuple(sorted(truncate_id(s) for s in sessions)),
        unverified_rows=len(part.unverified),
        skipped_transcripts=len(part.skipped_sessions),
    )
