#!/usr/bin/env python3
"""mutation_report.py — parse a Stryker mutation-report.json and compute scores.

Generic, stdlib-only, cross-platform (macOS, Linux, Windows). Sole runtime
dependency is python3 (>= 3.8) on PATH. Carries no repo-specific literal —
project names, controller names, and test-library names live in the report
being parsed, never in this module.

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
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

# Statuses that participate in the score denominators.
_KILLED = "Killed"
_SURVIVED = "Survived"
_TIMEOUT = "Timeout"
_NO_COVERAGE = "NoCoverage"


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


def score_report(report_path: Path) -> ScoreSummary:
    """Compute the honest and reported scores for a mutation report.

    Returns a fully zeroed :class:`ScoreSummary` when the report is absent
    or empty — never raises for a missing file.
    """
    data = _load_report(report_path)

    killed = survived = timeout = no_coverage = 0
    for mutant in _iter_mutants(data):
        status = mutant.get("status")
        if status == _KILLED:
            killed += 1
        elif status == _SURVIVED:
            survived += 1
        elif status == _TIMEOUT:
            timeout += 1
        elif status == _NO_COVERAGE:
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


def survivors_by_mutator(report_path: Path, file_path: str) -> Dict[str, List[dict]]:
    """Return the Survived mutants for one source file, grouped by mutator name.

    Matches ``file_path`` against report keys by exact match first, then by
    basename, so a caller can pass either the full report key or just the
    filename. Only ``Survived`` mutants are returned — killed, timed-out, and
    uncovered mutants are not survivors. Returns ``{}`` when the file is not
    in the report or has no survivors.
    """
    data = _load_report(report_path)
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
        if mutant.get("status") != _SURVIVED:
            continue
        mutator = mutant.get("mutatorName", "")
        grouped.setdefault(mutator, []).append(mutant)
    return grouped
