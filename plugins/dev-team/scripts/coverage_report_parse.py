#!/usr/bin/env python3
"""coverage_report_parse.py — shared per-format coverage report parsers
(issue #1873).

"What a coverage report means" used to be modeled twice: once as prose in
`coverage-baseline/SKILL.md` / `references/multi-project-discovery.md`
(instructing the *agent* to parse a report's raw counts by hand), and once as
code in `coverage_gap_ranking.py`'s seven per-format parsers — under a
different vocabulary (`lines_total`/`lines_covered`/`branches_total`/
`branches_covered`) than `coverage_config.weighted_merge` already required
(`covered_statements`/`total_statements`/`covered_branches`/
`total_branches`). This module is the one implementation: it owns format
detection and every per-format parser, and returns `CoverageRecord`s using
`coverage_config`'s vocabulary directly, so no translation layer is needed
between a parsed report and `weighted_merge`.

Supported formats (auto-detected):

| Format            | Detected by                              | Module key      |
|-------------------|------------------------------------------|-----------------|
| `lcov`            | `SF:` records                            | path prefix     |
| `cobertura`       | XML root `<coverage>` with `<packages>`  | path prefix     |
| `clover`          | XML root `<coverage clover="...">`       | path prefix     |
| `jacoco-csv`      | CSV header with `LINE_MISSED`            | `PACKAGE`       |
| `istanbul-summary`| JSON with a `total.lines` block          | path prefix     |
| `istanbul-final`  | JSON whose file entries carry `s`/`b`    | path prefix     |
| `coverage-py`     | JSON with `files` + `totals`             | path prefix     |
| `coverlet`        | JSON assembly -> file -> class -> method | assembly name   |

Clover's root element is also `<coverage ...>` (like Cobertura's), so the
two are disambiguated by the presence of Clover's own `clover="..."`
attribute on that root element — see `detect_format`.

A recognized-but-effectively-empty report (a format detects cleanly but
parses to zero records) is treated as a parse failure (`ReportError`), not a
silent 0% measurement — see `parse_report`'s docstring.

Callers with their own internal vocabulary (`coverage_gap_ranking.py`'s
`lines_total`/...) translate `CoverageRecord` at their own module boundary;
`coverage_config.weighted_merge` accepts `CoverageRecord`s (or `aggregate()`'s
output) directly — see that function's docstring.

Stdlib-only (ADR 0014/0015), Python 3.10+ floor (ADR 0031).
"""

from __future__ import annotations

import csv
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import coverage_config

_CONDITION_RE = re.compile(r"\((\d+)/(\d+)\)")
_COVERAGE_ROOT_RE = re.compile(r"<coverage\b([^>]*)>", re.IGNORECASE)


class ReportError(ValueError):
    """A report could not be read, recognized, or parsed."""


@dataclass(frozen=True)
class CoverageRecord:
    """One file's (or, via `aggregate()`, one project's) coverage counts,
    using `coverage_config.weighted_merge`'s required field names."""

    covered_statements: int
    total_statements: int
    covered_branches: int = 0
    total_branches: int = 0
    path: str | None = None
    module: str | None = None


# ---------------------------------------------------------------------------
# format detection
# ---------------------------------------------------------------------------


def _detect_json_format(payload: object) -> str:
    if not isinstance(payload, dict) or not payload:
        raise ReportError("unrecognized coverage report format (empty JSON object)")
    if "files" in payload and "totals" in payload:
        return "coverage-py"
    total = payload.get("total")
    if isinstance(total, dict) and "lines" in total:
        return "istanbul-summary"
    first = next(iter(payload.values()))
    if isinstance(first, dict) and ("s" in first or "statementMap" in first):
        return "istanbul-final"
    if isinstance(first, dict) and _looks_like_coverlet_assembly(first):
        return "coverlet"
    raise ReportError("unrecognized coverage report format (JSON)")


def _looks_like_coverlet_assembly(assembly: dict) -> bool:
    """Coverlet nests assembly -> file -> class -> method -> {"Lines": {...}}."""
    for classes in assembly.values():
        if not isinstance(classes, dict):
            return False
        for methods in classes.values():
            if isinstance(methods, dict) and any(
                isinstance(m, dict) and "Lines" in m for m in methods.values()
            ):
                return True
    return False


def _read(path: Path) -> str:
    """Read a report as text. `utf-8-sig` strips a UTF-8 BOM if present —
    .NET/Windows coverage writers emit them, and a BOM is not whitespace, so
    it would otherwise defeat every branch of `detect_format`."""
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:  # pragma: no cover - surfaced by caller as exit 2
        raise ReportError(f"{path}: {exc}") from exc


def detect_format(path: Path) -> str:
    """Return the format id for `path`, raising ReportError when unrecognized.

    Clover and Cobertura both root the document on a bare `<coverage ...>`
    element, so a substring check for `"<coverage"` alone cannot tell them
    apart — it previously classified every Clover report as Cobertura, whose
    parser then silently skipped every `<class>` element (Clover's carry a
    `name` attribute, not Cobertura's `filename`) and returned zero records.
    Disambiguate on the root element's own attributes: only Clover's root
    carries a `clover="..."` attribute.
    """
    text = _read(path)

    stripped = text.lstrip()
    if stripped.startswith("<"):
        root_match = _COVERAGE_ROOT_RE.search(text)
        if root_match:
            return "clover" if "clover=" in root_match.group(1) else "cobertura"
        raise ReportError(f"unrecognized coverage report format: {path}")
    if stripped.startswith(("{", "[")):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ReportError(f"{path}: not valid JSON ({exc.msg})") from exc
        return _detect_json_format(payload)
    if re.search(r"^SF:", text, re.MULTILINE) or re.search(r"^TN:", text, re.MULTILINE):
        return "lcov"
    header = text.splitlines()[0] if text.splitlines() else ""
    if "LINE_MISSED" in header:
        return "jacoco-csv"
    raise ReportError(f"unrecognized coverage report format: {path}")


# ---------------------------------------------------------------------------
# per-format parsers — each returns a list of CoverageRecord
# ---------------------------------------------------------------------------


def _record(
    path: str,
    total_statements: int,
    covered_statements: int,
    total_branches: int = 0,
    covered_branches: int = 0,
    module: str | None = None,
) -> CoverageRecord:
    return CoverageRecord(
        covered_statements=covered_statements,
        total_statements=total_statements,
        covered_branches=covered_branches,
        total_branches=total_branches,
        path=path,
        module=module,
    )


def _parse_lcov(text: str) -> list[CoverageRecord]:
    records: list[CoverageRecord] = []
    current: dict | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("SF:"):
            current = {
                "path": line[3:],
                "lf": None,
                "lh": None,
                "brf": None,
                "brh": None,
                "da_total": 0,
                "da_hit": 0,
            }
        elif current is None:
            continue
        elif line.startswith("DA:"):
            parts = line[3:].split(",")
            if len(parts) >= 2:
                current["da_total"] += 1
                current["da_hit"] += 1 if _int(parts[1]) > 0 else 0
        elif line.startswith("LF:"):
            current["lf"] = _int(line[3:])
        elif line.startswith("LH:"):
            current["lh"] = _int(line[3:])
        elif line.startswith("BRF:"):
            current["brf"] = _int(line[4:])
        elif line.startswith("BRH:"):
            current["brh"] = _int(line[4:])
        elif line.startswith("end_of_record"):
            records.append(_lcov_record(current))
            current = None
    if current is not None:
        records.append(_lcov_record(current))
    return records


def _lcov_record(entry: dict) -> CoverageRecord:
    # LF/LH are the summary lines; fall back to tallied DA: records for
    # writers that emit only line-level data.
    total = entry["lf"] if entry["lf"] is not None else entry["da_total"]
    covered = entry["lh"] if entry["lh"] is not None else entry["da_hit"]
    return _record(
        entry["path"],
        total,
        covered,
        entry["brf"] or 0,
        entry["brh"] or 0,
    )


def _int(value: str) -> int:
    try:
        return int(value.strip())
    except (TypeError, ValueError):
        return 0


def _parse_cobertura(text: str) -> list[CoverageRecord]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ReportError(f"cobertura report is not valid XML ({exc})") from exc
    records: list[CoverageRecord] = []
    for cls in root.iter("class"):
        filename = cls.get("filename")
        if not filename:
            continue
        # A Cobertura writer may list the same source line twice inside one
        # <class> — once under <methods>/<method>/<lines> and again in the
        # class-level <lines> block (coverlet's cobertura reporter does). The
        # descendant walk sees both, so tally per line NUMBER and keep the best
        # hit/condition figures; a plain running count would inflate
        # lines_total, uncovered_lines, and every ranking magnitude derived
        # from them, unevenly across classes.
        by_line: dict[str, tuple[int, int, int]] = {}
        for index, line in enumerate(cls.iter("line")):
            key = line.get("number") or f"#{index}"
            hits = _int(line.get("hits") or "0")
            covered, total = _condition_counts(line.get("condition-coverage"))
            prior = by_line.get(key)
            if prior is None:
                by_line[key] = (hits, covered, total)
            else:
                by_line[key] = (
                    max(prior[0], hits),
                    max(prior[1], covered),
                    max(prior[2], total),
                )
        lines_total = len(by_line)
        lines_covered = sum(1 for hits, _c, _t in by_line.values() if hits > 0)
        branches_covered = sum(covered for _h, covered, _t in by_line.values())
        branches_total = sum(total for _h, _c, total in by_line.values())
        records.append(
            _record(filename, lines_total, lines_covered, branches_total, branches_covered)
        )
    return records


def _parse_clover(text: str) -> list[CoverageRecord]:
    """Clover carries per-file totals directly on each `<file>` element's own
    `<metrics>` child — unlike Cobertura, no per-line reconstruction is
    needed. `<class>` elements here carry a `name` attribute, not
    Cobertura's `filename` — a Clover document routed to `_parse_cobertura`
    (its `<class>` lookup keys on `filename`) would silently skip every
    class and return zero records; this parser reads the `<file>`/`<metrics>`
    pair Clover actually populates."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ReportError(f"clover report is not valid XML ({exc})") from exc
    records: list[CoverageRecord] = []
    for file_el in root.iter("file"):
        metrics = file_el.find("metrics")
        if metrics is None:
            continue
        name = file_el.get("path") or file_el.get("name")
        if not name:
            continue
        records.append(
            _record(
                name,
                _int(metrics.get("statements") or "0"),
                _int(metrics.get("coveredstatements") or "0"),
                _int(metrics.get("conditionals") or "0"),
                _int(metrics.get("coveredconditionals") or "0"),
            )
        )
    return records


def _condition_counts(condition_coverage: str | None) -> tuple[int, int]:
    """`50% (1/2)` -> (1, 2); anything else -> (0, 0)."""
    if not condition_coverage:
        return (0, 0)
    match = _CONDITION_RE.search(condition_coverage)
    if not match:
        return (0, 0)
    return (int(match.group(1)), int(match.group(2)))


def _parse_jacoco_csv(text: str) -> list[CoverageRecord]:
    rows = list(csv.DictReader(text.splitlines()))
    records = []
    for row in rows:
        package = (row.get("PACKAGE") or "").strip() or "(default)"
        cls = (row.get("CLASS") or "").strip()
        line_missed = _int(row.get("LINE_MISSED") or "0")
        line_covered = _int(row.get("LINE_COVERED") or "0")
        branch_missed = _int(row.get("BRANCH_MISSED") or "0")
        branch_covered = _int(row.get("BRANCH_COVERED") or "0")
        records.append(
            _record(
                f"{package}/{cls}" if cls else package,
                line_missed + line_covered,
                line_covered,
                branch_missed + branch_covered,
                branch_covered,
                module=package,
            )
        )
    return records


def _parse_istanbul_summary(payload: dict) -> list[CoverageRecord]:
    records = []
    for path, entry in payload.items():
        if path == "total" or not isinstance(entry, dict):
            continue
        lines = entry.get("lines") or {}
        branches = entry.get("branches") or {}
        records.append(
            _record(
                path,
                _int(str(lines.get("total", 0))),
                _int(str(lines.get("covered", 0))),
                _int(str(branches.get("total", 0))),
                _int(str(branches.get("covered", 0))),
            )
        )
    return records


def _parse_istanbul_final(payload: dict) -> list[CoverageRecord]:
    records = []
    for key, entry in payload.items():
        if not isinstance(entry, dict):
            continue
        statements = entry.get("s") or {}
        lines_total = len(statements)
        lines_covered = sum(1 for hits in statements.values() if _as_int(hits) > 0)
        branches_total = branches_covered = 0
        for arm_hits in (entry.get("b") or {}).values():
            if not isinstance(arm_hits, list):
                continue
            branches_total += len(arm_hits)
            branches_covered += sum(1 for hits in arm_hits if _as_int(hits) > 0)
        records.append(
            _record(
                entry.get("path") or key,
                lines_total,
                lines_covered,
                branches_total,
                branches_covered,
            )
        )
    return records


def _as_int(value: object) -> int:
    return value if isinstance(value, int) else _int(str(value))


def _parse_coverage_py(payload: dict) -> list[CoverageRecord]:
    records = []
    for path, entry in (payload.get("files") or {}).items():
        summary = (entry or {}).get("summary") or {}
        records.append(
            _record(
                path,
                _as_int(summary.get("num_statements", 0)),
                _as_int(summary.get("covered_lines", 0)),
                _as_int(summary.get("num_branches", 0)),
                _as_int(summary.get("covered_branches", 0)),
            )
        )
    return records


def _tally_coverlet_classes(classes: dict) -> tuple[int, int, int, int]:
    """Tally one file's `classes` dict (coverlet's class -> method ->
    {"Lines", "Branches"} nesting) into `(lines_total, lines_covered,
    branches_total, branches_covered)`."""
    lines_total = lines_covered = branches_total = branches_covered = 0
    for methods in (classes or {}).values():
        if not isinstance(methods, dict):
            continue
        for method in methods.values():
            if not isinstance(method, dict):
                continue
            for hits in (method.get("Lines") or {}).values():
                lines_total += 1
                lines_covered += 1 if _as_int(hits) > 0 else 0
            for branch in method.get("Branches") or []:
                branches_total += 1
                branches_covered += 1 if _as_int(branch.get("Hits", 0)) > 0 else 0
    return lines_total, lines_covered, branches_total, branches_covered


def _parse_coverlet(payload: dict) -> list[CoverageRecord]:
    records = []
    for assembly, files in payload.items():
        if not isinstance(files, dict):
            continue
        for file_path, classes in files.items():
            lines_total, lines_covered, branches_total, branches_covered = (
                _tally_coverlet_classes(classes)
            )
            records.append(
                _record(
                    file_path,
                    lines_total,
                    lines_covered,
                    branches_total,
                    branches_covered,
                    module=assembly,
                )
            )
    return records


_JSON_PARSERS = {
    "istanbul-summary": _parse_istanbul_summary,
    "istanbul-final": _parse_istanbul_final,
    "coverage-py": _parse_coverage_py,
    "coverlet": _parse_coverlet,
}


def parse_report(path: Path, fmt: str) -> list[CoverageRecord]:
    """Parse `path` as `fmt`, returning one `CoverageRecord` per source file.

    Raises `ReportError` when `fmt` is a recognized format but the parse
    produces zero records. A report that legitimately covers zero
    statements is indistinguishable, at this layer, from a misdetected or
    malformed report that silently parsed to nothing — treating "recognized
    format, zero records" as a parse failure (rather than passing an
    empty-but-valid-looking result on to `aggregate()`/`weighted_merge`,
    which would read it as a genuine 0% coverage measurement) is what
    surfaces that ambiguity instead of hiding it.
    """
    if fmt in ("cobertura", "clover"):
        # Both formats are parsed with `ET.fromstring` — route them through
        # the shared DOCTYPE/ENTITY screen (issue #1872) rather than `_read`.
        # Other formats are unaffected.
        data, err = coverage_config.read_and_screen_xml(path)
        if err is not None:
            raise ReportError(err["message"])
        text = data.decode("utf-8-sig", errors="replace")
        records = _parse_clover(text) if fmt == "clover" else _parse_cobertura(text)
    elif fmt == "lcov":
        records = _parse_lcov(_read(path))
    elif fmt == "jacoco-csv":
        records = _parse_jacoco_csv(_read(path))
    else:
        parser = _JSON_PARSERS.get(fmt)
        if parser is None:
            raise ReportError(f"no parser for format {fmt!r}")
        text = _read(path)
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ReportError(f"{path}: not valid JSON ({exc.msg})") from exc
        records = parser(payload)

    if not records:
        raise ReportError(
            f"{path}: recognized as {fmt!r} but parsed to zero records — "
            "treating this as a parse failure rather than a 0% coverage "
            "measurement"
        )
    return records


def parse(path: Path) -> list[CoverageRecord]:
    """Detect `path`'s format and parse it — the one-call path
    `coverage-baseline`'s multi-project merge (and any other caller with no
    reason to detect and parse separately) uses."""
    return parse_report(path, detect_format(path))


def aggregate(records: list[CoverageRecord]) -> CoverageRecord:
    """Sum per-file records into one project-level total — the shape
    `coverage_config.weighted_merge` requires per included project. Used by
    the multi-project coverage-baseline merge to turn one project's parsed
    report into the single entry it contributes to `weighted_merge`'s input
    list."""
    return CoverageRecord(
        covered_statements=sum(r.covered_statements for r in records),
        total_statements=sum(r.total_statements for r in records),
        covered_branches=sum(r.covered_branches for r in records),
        total_branches=sum(r.total_branches for r in records),
    )
