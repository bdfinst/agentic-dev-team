"""Parser for the pre-registration's single machine-readable block.

``preregistration.md`` holds exactly one fenced block whose info string is
``json prereg``. It is the only place metric thresholds live: the audit and
the report read it, and nothing else carries a copy. Any empty cell, bad
threshold or inconsistent identity declaration is malformed input (exit 2)
that names the metric and the column.

Stdlib-only.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from . import streams
from .streams import InputError

FENCE_INFO = "json prereg"

OPERATORS = ("<", "<=", ">", ">=")
INCLUSIVITY = {"<=": "inclusive", ">=": "inclusive", "<": "exclusive", ">": "exclusive"}
HANDLINGS = ("UNVERIFIED", "unmeasurable")
PARITY_CAPS = ("tune", "none")
#: Instrument value for a metric no stream can measure.
NO_INSTRUMENT = "none"

#: Cells that must be non-empty in every metric entry.
REQUIRED_COLUMNS = (
    "id",
    "metric",
    "instrument",
    "identity_class",
    "baseline",
    "keep",
    "tune",
    "retire",
    "direction",
    "inclusivity",
    "minimum_n",
    "null_rule",
    "parity_cap",
    "window",
    "confounds",
    "computation",
)
THRESHOLD_COLUMNS = ("keep", "tune", "retire")

_THRESHOLD = re.compile(r"^\s*(<=|>=|<|>)\s*(-?\d+(?:\.\d+)?)\s*$")
_FENCE = re.compile(r"^(`{3,})\s*(.*?)\s*$")


@dataclass(frozen=True)
class Threshold:
    op: str
    limit: float


@dataclass(frozen=True)
class Metric:
    id: str
    metric: str
    instrument: str
    identity_class: str
    id_less_handling: str | None
    baseline: str
    keep: Threshold
    tune: Threshold
    retire: Threshold
    direction: str
    inclusivity: str
    minimum_n: int
    n_unit: str
    null_rule: str
    parity_cap: str
    window: str
    confounds: tuple[str, ...]
    computation: str
    ceiling: float | None


@dataclass(frozen=True)
class Prereg:
    path: Path
    metrics: tuple[Metric, ...]

    def get(self, metric_id: str) -> Metric:
        return next(m for m in self.metrics if m.id == metric_id)


def parse_threshold(text: str) -> Threshold | None:
    """``"<= 450"`` -> ``Threshold("<=", 450.0)``; ``None`` when not a number with a direction."""
    match = _THRESHOLD.match(text) if isinstance(text, str) else None
    return Threshold(match.group(1), float(match.group(2))) if match else None


def _fenced_blocks(lines: list[str]) -> list[tuple[str, int, list[str]]]:
    """``(info, first_body_line_number, body)`` for each closed fence."""
    blocks, open_fence = [], None
    for number, line in enumerate(lines, start=1):
        match = _FENCE.match(line)
        if open_fence is None:
            if match:
                open_fence = (match.group(1), match.group(2), number + 1, [])
        elif match and not match.group(2) and len(match.group(1)) >= len(open_fence[0]):
            blocks.append((open_fence[1], open_fence[2], open_fence[3]))
            open_fence = None
        else:
            open_fence[3].append(line)
    return blocks


def _blank(value: object) -> bool:
    return value is None or (isinstance(value, (str, list, tuple, dict)) and not value)


def load_prereg(path: Path | str) -> Prereg:
    path = Path(path)
    text = streams.read_text(path)
    if text is None:
        raise InputError(
            path,
            0,
            "pre-registration file not found",
            "pass --prereg with the path to preregistration.md",
        )
    prereg_blocks = [b for b in _fenced_blocks(text.splitlines()) if b[0] == FENCE_INFO]
    if len(prereg_blocks) != 1:
        raise InputError(
            path,
            0,
            f"expected exactly one '{FENCE_INFO}' fenced block, found {len(prereg_blocks)}",
            f"keep a single ```{FENCE_INFO} block as the only source of values",
        )
    _, first_line, body = prereg_blocks[0]
    try:
        document = json.loads("\n".join(body))
    except ValueError as exc:
        raise InputError(
            path,
            first_line + getattr(exc, "lineno", 1) - 1,
            f"block is not valid JSON ({exc})",
            "fix the JSON syntax in the block",
        ) from exc
    entries = document.get("metrics") if isinstance(document, dict) else None
    if not isinstance(entries, list) or not entries:
        raise InputError(
            path,
            first_line,
            "block has no 'metrics' list",
            "add one entry per pre-registered metric under 'metrics'",
        )
    locate = _line_locator(body, first_line)
    metrics, seen = [], set()
    for position, entry in enumerate(entries):
        metric = _parse_entry(path, entry, position, locate)
        if metric.id in seen:
            raise InputError(
                path,
                locate(metric.id),
                f"metric '{metric.id}' appears twice",
                "give each entry a unique id",
            )
        seen.add(metric.id)
        metrics.append(metric)
    return Prereg(path, tuple(metrics))


def _line_locator(body: list[str], first_line: int):
    def locate(metric_id: str) -> int:
        pattern = re.compile(r'"id"\s*:\s*' + re.escape(json.dumps(metric_id)))
        return next(
            (first_line + i for i, line in enumerate(body) if pattern.search(line)),
            first_line,
        )

    return locate


def _parse_entry(path: Path, entry: object, position: int, locate) -> Metric:
    if not isinstance(entry, dict):
        raise InputError(
            path,
            locate(""),
            f"metrics[{position}] is not an object",
            "write each metric as a JSON object",
        )
    metric_id = (
        entry.get("id")
        if isinstance(entry.get("id"), str) and entry.get("id")
        else f"metrics[{position}]"
    )
    line = locate(metric_id)

    def fail(column: str, problem: str, action: str) -> InputError:
        return InputError(
            path, line, f"metric '{metric_id}' column '{column}' {problem}", action
        )

    for column in REQUIRED_COLUMNS:
        if _blank(entry.get(column)):
            raise fail(
                column, "is empty", f"fill the '{column}' cell in the fenced block"
            )
    thresholds = {}
    for column in THRESHOLD_COLUMNS:
        parsed = parse_threshold(entry[column])
        if parsed is None:
            raise fail(
                column,
                f"is not a number with a direction ({', '.join(OPERATORS)}): {entry[column]!r}",
                f"write '{column}' as a direction and a number, for example \"<= 450\"",
            )
        thresholds[column] = parsed
    if entry["direction"] not in OPERATORS:
        raise fail(
            "direction",
            f"must be one of {', '.join(OPERATORS)}",
            "use the within-condition operator",
        )
    if entry["inclusivity"] != INCLUSIVITY[entry["direction"]]:
        raise fail(
            "inclusivity",
            f"must be '{INCLUSIVITY[entry['direction']]}' for direction '{entry['direction']}'",
            "make inclusivity agree with direction",
        )
    if (
        not isinstance(entry["minimum_n"], int)
        or isinstance(entry["minimum_n"], bool)
        or entry["minimum_n"] < 1
    ):
        raise fail(
            "minimum_n",
            "must be a positive integer",
            "write the smallest N that counts as data",
        )
    if entry["parity_cap"] not in PARITY_CAPS:
        raise fail(
            "parity_cap",
            f"must be one of {', '.join(PARITY_CAPS)}",
            "write 'tune' or 'none'",
        )
    if not isinstance(entry["confounds"], list) or not all(
        isinstance(c, str) and c for c in entry["confounds"]
    ):
        raise fail(
            "confounds",
            "must be a list of non-empty strings",
            "list each confound as a string",
        )
    handling = _check_identity(entry, fail)
    ceiling = entry.get("ceiling")
    if ceiling is not None and (
        isinstance(ceiling, bool) or not isinstance(ceiling, (int, float))
    ):
        raise fail(
            "ceiling", "must be a number when present", "write the ceiling as a number"
        )
    return Metric(
        id=metric_id,
        metric=entry["metric"],
        instrument=entry["instrument"],
        identity_class=entry["identity_class"],
        id_less_handling=handling,
        baseline=entry["baseline"],
        keep=thresholds["keep"],
        tune=thresholds["tune"],
        retire=thresholds["retire"],
        direction=entry["direction"],
        inclusivity=entry["inclusivity"],
        minimum_n=entry["minimum_n"],
        n_unit=entry.get("n_unit") or "rows",
        null_rule=entry["null_rule"],
        parity_cap=entry["parity_cap"],
        window=entry["window"],
        confounds=tuple(entry["confounds"]),
        computation=entry["computation"],
        ceiling=float(ceiling) if ceiling is not None else None,
    )


def _check_identity(entry: dict, fail) -> str | None:
    """Validate identity class against the instrument and return the id-less handling."""
    identity, instrument = entry["identity_class"], entry["instrument"]
    if identity not in (streams.ID_BEARING, streams.ID_LESS):
        raise fail(
            "identity_class",
            f"must be '{streams.ID_BEARING}' or '{streams.ID_LESS}'",
            "classify the instrument by whether its rows carry a session id",
        )
    spec = streams.STREAM_TABLE.get(instrument)
    expected = (
        spec.identity_class
        if spec
        else (
            streams.ID_BEARING
            if instrument == streams.MANUAL_INSTRUMENT
            else streams.ID_LESS
        )
    )
    if identity != expected:
        raise fail(
            "identity_class",
            f"must be '{expected}' for instrument '{instrument}'",
            "match the identity class to the instrument",
        )
    handling = entry.get("id_less_handling")
    if identity == streams.ID_BEARING:
        if handling is not None:
            raise fail(
                "id_less_handling",
                "must be absent for an id-bearing instrument",
                "remove the cell",
            )
        return None
    if handling not in HANDLINGS:
        raise fail(
            "id_less_handling",
            f"must be exactly one of {', '.join(HANDLINGS)}",
            "pick one handling for this id-less instrument",
        )
    if instrument == NO_INSTRUMENT and handling != "unmeasurable":
        raise fail(
            "id_less_handling",
            "must be 'unmeasurable' when the instrument is 'none'",
            "a metric with no instrument cannot be printed as UNVERIFIED",
        )
    return handling
