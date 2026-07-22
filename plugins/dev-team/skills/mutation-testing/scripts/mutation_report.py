#!/usr/bin/env python3
"""mutation_report.py — parse a native mutation report and compute scores.

Generic, stdlib-only, cross-platform (macOS, Linux, Windows). Sole runtime
dependency is python3 (>= 3.8) on PATH. Carries no repo-specific literal —
project names, controller names, and test-library names live in the report
being parsed, never in this module.

Two native report shapes are supported, normalized to the same internal
``{"files": {"<path>": {"mutants": [...]}}}`` dict before scoring:

- Stryker / Stryker.NET's own ``mutation-report.json`` — read directly via
  the path-based functions (``score_report``, ``survivors_by_mutator``, …).
- mutmut's ``mutmut junitxml`` output — mutmut has no JSON report of its
  own; ``parse_mutmut_junitxml`` converts it into the same internal shape so
  every downstream function (scoring, survivor extraction, file discovery)
  works identically regardless of which tool produced the data.

Two scores are computed side by side:

- **honest score** = Killed / (Killed + Survived + NoCoverage)
  A Timeout is *not* a demonstrated kill — the test never asserted anything;
  the mutant merely ran too long. Counting Timeouts as kills inflates the
  score, so the honest score excludes them from the numerator entirely.

- **reported score** = (Killed + Timeout) / (Killed + Survived + Timeout + NoCoverage)
  The score Stryker itself reports, kept alongside for parity so the gap
  between "what the tool claims" and "what the tests actually prove" is
  visible rather than hidden.

Both scores are expressed as percentages in [0, 100]. An absent or empty
report yields zeroed scores rather than raising.

Stryker.NET mutant statuses: Killed, Survived, Timeout, NoCoverage, Ignored,
CompileError. Only the first four participate in scoring; Ignored and
CompileError are excluded from both numerator and denominator.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

# Stryker.NET mutant-status vocabulary — the single source of truth for these
# literals across the whole pipeline. Sibling modules import these constants
# rather than re-typing the raw strings, so the status vocabulary lives in one
# place (AC4). Only these four participate in the score denominators.
STATUS_KILLED = "Killed"
STATUS_SURVIVED = "Survived"
STATUS_TIMEOUT = "Timeout"
STATUS_NO_COVERAGE = "NoCoverage"


@dataclass(frozen=True)
class ScoreSummary:
    """Both scores plus the two counts that distinguish them.

    ``honest_score`` and ``reported_score`` are percentages in [0, 100].
    ``timeout`` and ``no_coverage`` are raw mutant counts, surfaced so a
    caller can show *why* the two scores diverge.
    """

    killed: int
    survived: int
    timeout: int
    no_coverage: int
    honest_score: float
    reported_score: float


def _load_report(report_path: Path) -> dict:
    """Return the parsed report, or ``{}`` when the file is absent/empty."""
    path = Path(report_path)
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    return json.loads(text)


def _iter_mutants(data: dict):
    """Yield every mutant dict across all files in a parsed report."""
    for info in data.get("files", {}).values():
        for mutant in info.get("mutants", []):
            yield mutant


def _score_data(data: dict) -> ScoreSummary:
    """Compute the honest and reported scores for an already-parsed report
    dict (the ``{"files": {...}}`` shape shared by every supported tool)."""
    killed = survived = timeout = no_coverage = 0
    for mutant in _iter_mutants(data):
        status = mutant.get("status")
        if status == STATUS_KILLED:
            killed += 1
        elif status == STATUS_SURVIVED:
            survived += 1
        elif status == STATUS_TIMEOUT:
            timeout += 1
        elif status == STATUS_NO_COVERAGE:
            no_coverage += 1

    honest_denom = killed + survived + no_coverage
    reported_denom = killed + survived + timeout + no_coverage

    honest_score = (killed / honest_denom * 100) if honest_denom else 0.0
    reported_score = (
        (killed + timeout) / reported_denom * 100 if reported_denom else 0.0
    )

    return ScoreSummary(
        killed=killed,
        survived=survived,
        timeout=timeout,
        no_coverage=no_coverage,
        honest_score=honest_score,
        reported_score=reported_score,
    )


def score_report(report_path: Path) -> ScoreSummary:
    """Compute the honest and reported scores for a Stryker-shaped mutation
    report on disk.

    Returns a fully zeroed :class:`ScoreSummary` when the report is absent
    or empty — never raises for a missing file.
    """
    return _score_data(_load_report(report_path))


def _survivors_from_data(data: dict, file_path: str) -> Dict[str, List[dict]]:
    """Return the Survived mutants for one source file, grouped by mutator
    name, from an already-parsed report dict.

    Matches ``file_path`` against report keys by exact match first, then by
    basename, so a caller can pass either the full report key or just the
    filename. Only ``Survived`` mutants are returned — killed, timed-out, and
    uncovered mutants are not survivors. Returns ``{}`` when the file is not
    in the report or has no survivors.
    """
    files = data.get("files", {})

    info = files.get(file_path)
    if info is None:
        target = Path(file_path).name
        for key, value in files.items():
            if Path(key).name == target:
                info = value
                break
    if info is None:
        return {}

    grouped: Dict[str, List[dict]] = {}
    for mutant in info.get("mutants", []):
        if mutant.get("status") != STATUS_SURVIVED:
            continue
        mutator = mutant.get("mutatorName", "")
        grouped.setdefault(mutator, []).append(mutant)
    return grouped


def survivors_by_mutator(report_path: Path, file_path: str) -> Dict[str, List[dict]]:
    """Return the Survived mutants for one source file, grouped by mutator
    name, from a Stryker-shaped mutation report on disk."""
    return _survivors_from_data(_load_report(report_path), file_path)


def _files_with_status_from_data(data: dict, status: str) -> List[str]:
    """Return the sorted report file keys having >= 1 mutant of ``status``,
    from an already-parsed report dict.

    The report keys are the file identifiers exactly as the tool emits them
    (relative source paths); the caller decides how to interpret them.
    """
    return sorted(
        key
        for key, info in data.get("files", {}).items()
        if any(m.get("status") == status for m in info.get("mutants", []))
    )


def _files_with_status(report_path: Path, status: str) -> List[str]:
    """Return the sorted report file keys having >= 1 mutant of ``status``,
    from a Stryker-shaped mutation report on disk. Returns ``[]`` for an
    absent/empty report — never raises."""
    return _files_with_status_from_data(_load_report(report_path), status)


def files_with_survivors(report_path: Path) -> List[str]:
    """Return the sorted report file keys that have >= 1 Survived mutant.

    This is the single source of truth for survivor-file discovery — sibling
    modules call it instead of re-walking the report (AC4).
    """
    return _files_with_status(report_path, STATUS_SURVIVED)


def files_with_timeouts(report_path: Path) -> List[str]:
    """Return the sorted report file keys that have >= 1 Timeout mutant.

    This is the single source of truth for timeout-file discovery — sibling
    modules call it instead of re-walking the report (AC4).
    """
    return _files_with_status(report_path, STATUS_TIMEOUT)


# =============================================================================
# mutmut — no native JSON report; junitxml is its only structured output.
# =============================================================================
def parse_mutmut_junitxml(xml_text: str) -> dict:
    """Convert ``mutmut junitxml`` output into the internal ``{"files": {...}}``
    shape every scoring/survivor function above already consumes.

    mutmut marks a survived mutant with a ``<failure>`` child
    (``message="bad_survived"``) and a timed-out mutant with a distinct
    ``<error>`` child (``message="bad_timeout"``, ``error_type="timeout"``) —
    the two are never conflated, so a real Timeout is never miscounted as a
    Survived. Every other ``<testcase>`` — including a suspicious-but-ignored
    mutant under mutmut's default ``suspicious_policy="ignore"`` — is Killed;
    mutmut's default reporting granularity cannot distinguish "cleanly
    killed" from "suspicious but ignored" any further than that. mutmut has
    no NoCoverage concept (it always runs the full scoped test command
    against every mutant), so that count is always zero here.

    Malformed or empty input returns an empty ``{"files": {}}`` rather than
    raising — callers see it as an empty report, same as a missing file.
    """
    files: Dict[str, dict] = {}
    if not xml_text.strip():
        return {"files": files}
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return {"files": files}

    for testcase in root.iter("testcase"):
        file_key = testcase.get("file")
        if not file_key:
            continue
        if testcase.find("failure") is not None:
            status = STATUS_SURVIVED
        elif testcase.find("error") is not None:
            status = STATUS_TIMEOUT
        else:
            status = STATUS_KILLED
        line = testcase.get("line")
        mutant = {
            "id": testcase.get("name", "?"),
            "mutatorName": "mutmut",
            "status": status,
            "location": {
                "start": {"line": int(line) if line and line.isdigit() else None}
            },
            "replacement": "",
        }
        files.setdefault(file_key, {"mutants": []})["mutants"].append(mutant)

    return {"files": files}


def score_mutmut_junitxml(xml_text: str) -> ScoreSummary:
    """Compute the honest and reported scores directly from ``mutmut
    junitxml`` output (no report file on disk needed)."""
    return _score_data(parse_mutmut_junitxml(xml_text))


def survivors_from_mutmut_junitxml(
    xml_text: str, file_path: str
) -> Dict[str, List[dict]]:
    """Return the Survived mutants for one file from ``mutmut junitxml``
    output, grouped by mutator name (always ``"mutmut"`` — the tool names no
    per-mutation operator the way Stryker/pitest do)."""
    return _survivors_from_data(parse_mutmut_junitxml(xml_text), file_path)
