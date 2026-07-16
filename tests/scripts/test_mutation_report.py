"""Pytest tests for mutation_report.py — the honest-score report module
(Slice 1 of the ACI mutation-pipeline fold, #1136).

Each test maps to a Slice 1 Gherkin scenario in
``plans/generalize-aci-mutation-pipeline-fold-into-mutation-kill.md``. The
report fixtures are minimal Stryker mutation-report.json shapes written to a
temp file; the exact scenario counts (10 Killed, 5 Survived, 3 NoCoverage,
4 Timeout) are asserted verbatim.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Ensure the module's dir is on the path so we can import it directly.
SCRIPTS_DIR = (
    Path(__file__).resolve().parents[2]
    / "plugins"
    / "dev-team"
    / "skills"
    / "mutation-testing"
    / "scripts"
)
sys.path.insert(0, str(SCRIPTS_DIR))

import mutation_report  # noqa: E402


# =============================================================================
# Fixture helpers
# =============================================================================
def _mutant(status: str, mutator: str = "ArithmeticOperator") -> dict:
    return {"id": f"{mutator}-{status}", "mutatorName": mutator, "status": status}


def _write_report(path: Path, files: dict) -> Path:
    path.write_text(json.dumps({"files": files}), encoding="utf-8")
    return path


def _report_with_counts(
    path: Path,
    *,
    killed: int = 0,
    survived: int = 0,
    no_coverage: int = 0,
    timeout: int = 0,
) -> Path:
    mutants = (
        [_mutant("Killed") for _ in range(killed)]
        + [_mutant("Survived") for _ in range(survived)]
        + [_mutant("NoCoverage") for _ in range(no_coverage)]
        + [_mutant("Timeout") for _ in range(timeout)]
    )
    return _write_report(path, {"src/Widget.cs": {"mutants": mutants}})


# =============================================================================
# Scenario: Both scores are computed with fully specified formulas
# =============================================================================
def test_both_scores_computed_with_specified_formulas(tmp_path: Path):
    report = _report_with_counts(
        tmp_path / "mutation-report.json",
        killed=10,
        survived=5,
        no_coverage=3,
        timeout=4,
    )

    summary = mutation_report.score_report(report)

    # honest = 10 / (10 + 5 + 3), reported = (10 + 4) / (10 + 5 + 4 + 3)
    assert summary.honest_score == pytest.approx(10 / 18 * 100)
    assert summary.reported_score == pytest.approx(14 / 22 * 100)
    assert summary.timeout == 4
    assert summary.no_coverage == 3
    assert summary.killed == 10
    assert summary.survived == 5


# =============================================================================
# Scenario: A timeout-heavy report yields a lower honest score than reported
# =============================================================================
def test_timeout_heavy_report_honest_strictly_lower_than_reported(tmp_path: Path):
    report = _report_with_counts(
        tmp_path / "mutation-report.json",
        killed=2,
        survived=1,
        no_coverage=0,
        timeout=20,
    )

    summary = mutation_report.score_report(report)

    assert summary.honest_score < summary.reported_score


# =============================================================================
# Scenario: An absent or empty report does not crash
# =============================================================================
def test_absent_report_returns_zeroed_scores_without_raising(tmp_path: Path):
    summary = mutation_report.score_report(tmp_path / "does-not-exist.json")

    assert summary.honest_score == 0.0
    assert summary.reported_score == 0.0
    assert summary.killed == 0
    assert summary.survived == 0
    assert summary.timeout == 0
    assert summary.no_coverage == 0


def test_empty_report_file_returns_zeroed_scores(tmp_path: Path):
    empty = tmp_path / "mutation-report.json"
    empty.write_text("", encoding="utf-8")

    summary = mutation_report.score_report(empty)

    assert summary.honest_score == 0.0
    assert summary.reported_score == 0.0


# =============================================================================
# Scenario: Survivors are extracted per file grouped by mutator
# =============================================================================
def test_survivors_extracted_per_file_grouped_by_mutator(tmp_path: Path):
    report = _write_report(
        tmp_path / "mutation-report.json",
        {
            "src/Widget.cs": {
                "mutants": [
                    _mutant("Survived", "ArithmeticOperator"),
                    _mutant("Survived", "ArithmeticOperator"),
                    _mutant("Survived", "EqualityOperator"),
                    _mutant("Killed", "ArithmeticOperator"),
                    _mutant("Timeout", "BlockStatement"),
                    _mutant("NoCoverage", "EqualityOperator"),
                ]
            },
            "src/Other.cs": {"mutants": [_mutant("Survived", "LogicalOperator")]},
        },
    )

    grouped = mutation_report.survivors_by_mutator(report, "src/Widget.cs")

    # Only Survived mutants, grouped by mutator name.
    assert set(grouped) == {"ArithmeticOperator", "EqualityOperator"}
    assert len(grouped["ArithmeticOperator"]) == 2
    assert len(grouped["EqualityOperator"]) == 1
    assert all(m["status"] == "Survived" for ms in grouped.values() for m in ms)


def test_survivors_lookup_by_basename(tmp_path: Path):
    report = _write_report(
        tmp_path / "mutation-report.json",
        {"/abs/src/Widget.cs": {"mutants": [_mutant("Survived", "LogicalOperator")]}},
    )

    grouped = mutation_report.survivors_by_mutator(report, "Widget.cs")

    assert set(grouped) == {"LogicalOperator"}


def test_survivors_for_unknown_file_is_empty(tmp_path: Path):
    report = _write_report(
        tmp_path / "mutation-report.json",
        {"src/Widget.cs": {"mutants": [_mutant("Survived")]}},
    )

    assert mutation_report.survivors_by_mutator(report, "src/Nope.cs") == {}


# =============================================================================
# Scenario: The module carries no repo-specific literal
# =============================================================================
def test_module_source_carries_no_repo_specific_literal():
    source = (SCRIPTS_DIR / "mutation_report.py").read_text(encoding="utf-8")

    forbidden = [
        "Aci.Speedpay",
        "Controllers",
        "AwesomeAssertions",
        "Moq",
        "AutoFixture",
    ]
    present = [literal for literal in forbidden if literal in source]
    assert present == [], f"repo-specific literals leaked into module: {present}"
