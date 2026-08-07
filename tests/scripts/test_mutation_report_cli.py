"""Pytest tests for mutation_report_cli.py — the CLI wrapper exposing
mutation_report.py's survivors_by_line() and survivors_by_mutator() as JSON
on stdout (#1937, Step 1.4).

Each test maps to a Slice 1 Gherkin scenario in
``plans/mutation-report-prose-extraction.md``. ``main()`` is invoked
directly, in-process (not subprocess), matching mutation_report.py's own
stdlib-only/no-subprocess test style.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from _mutation_test_helpers import SCRIPTS_DIR

sys.path.insert(0, str(SCRIPTS_DIR))

import mutation_report
import mutation_report_cli as cli


# =============================================================================
# Fixture helpers
# =============================================================================
def _mutant(status: str, mutator: str = "ArithmeticOperator", static: bool | None = None) -> dict:
    m = {"id": f"{mutator}-{status}", "mutatorName": mutator, "status": status}
    if static is not None:
        m["static"] = static
    return m


def _write_report(path: Path, files: dict) -> Path:
    path.write_text(json.dumps({"files": files}), encoding="utf-8")
    return path


# =============================================================================
# --survivors-by-line
# =============================================================================


def test_survivors_by_line_matches_library_call(tmp_path: Path, capsys) -> None:
    report = _write_report(
        tmp_path / "mutation.json",
        {"src/calc.ts": {"mutants": [_mutant("Survived"), _mutant("Killed")]}},
    )
    rc = cli.main(
        ["--survivors-by-line", "--report", str(report), "--file", "src/calc.ts"]
    )
    assert rc == 0
    out = capsys.readouterr()
    assert out.err == ""
    printed = json.loads(out.out)
    expected = mutation_report.survivors_by_line(report, "src/calc.ts")
    assert printed == expected


def test_survivors_by_line_missing_report_file_is_empty_json(
    tmp_path: Path, capsys
) -> None:
    missing = tmp_path / "does-not-exist.json"
    rc = cli.main(
        ["--survivors-by-line", "--report", str(missing), "--file", "src/calc.ts"]
    )
    assert rc == 0
    out = capsys.readouterr()
    assert json.loads(out.out) == {"clusters": [], "unclustered": []}


# =============================================================================
# --survivors-by-mutator
# =============================================================================


def test_survivors_by_mutator_matches_library_call(tmp_path: Path, capsys) -> None:
    report = _write_report(
        tmp_path / "mutation.json",
        {"src/calc.ts": {"mutants": [_mutant("Survived"), _mutant("Killed")]}},
    )
    rc = cli.main(
        ["--survivors-by-mutator", "--report", str(report), "--file", "src/calc.ts"]
    )
    assert rc == 0
    out = capsys.readouterr()
    printed = json.loads(out.out)
    expected = mutation_report.survivors_by_mutator(report, "src/calc.ts")
    assert printed == expected


def test_skip_static_matches_library_call_and_is_silent_when_field_present(
    tmp_path: Path, capsys
) -> None:
    report = _write_report(
        tmp_path / "mutation.json",
        {
            "src/calc.ts": {
                "mutants": [
                    _mutant("Survived", mutator="StringLiteral", static=True),
                    _mutant("Survived", mutator="ArithmeticOperator", static=False),
                ]
            }
        },
    )
    rc = cli.main(
        [
            "--survivors-by-mutator",
            "--report",
            str(report),
            "--file",
            "src/calc.ts",
            "--skip-static",
        ]
    )
    assert rc == 0
    out = capsys.readouterr()
    assert out.err == ""
    printed = json.loads(out.out)
    expected = mutation_report.survivors_by_mutator(
        report, "src/calc.ts", skip_static=True
    )
    assert printed == expected
    assert "StringLiteral" not in printed
    assert "ArithmeticOperator" in printed


def test_skip_static_notice_when_field_absent_on_matched_file(
    tmp_path: Path, capsys
) -> None:
    report = _write_report(
        tmp_path / "mutation.json",
        {"src/calc.ts": {"mutants": [_mutant("Survived")]}},
    )
    rc = cli.main(
        [
            "--survivors-by-mutator",
            "--report",
            str(report),
            "--file",
            "src/calc.ts",
            "--skip-static",
        ]
    )
    assert rc == 0
    out = capsys.readouterr()
    assert "skip-static" in out.err
    assert "src/calc.ts" in out.err
    assert "inapplicable" in out.err
    # JSON unaffected: every Survived mutant still present, unfiltered.
    printed = json.loads(out.out)
    expected = mutation_report.survivors_by_mutator(report, "src/calc.ts")
    assert printed == expected


def test_skip_static_notice_when_file_absent_from_report(
    tmp_path: Path, capsys
) -> None:
    report = _write_report(
        tmp_path / "mutation.json",
        {"src/other.ts": {"mutants": [_mutant("Survived")]}},
    )
    rc = cli.main(
        [
            "--survivors-by-mutator",
            "--report",
            str(report),
            "--file",
            "src/calc.ts",
            "--skip-static",
        ]
    )
    assert rc == 0
    out = capsys.readouterr()
    assert "skip-static" in out.err
    assert "inapplicable" in out.err
    assert "is not present in the report" in out.err
    assert "src/calc.ts" in out.err
    assert json.loads(out.out) == {}


# =============================================================================
# Argument errors
# =============================================================================


def test_both_mode_flags_is_argument_error(tmp_path: Path, capsys) -> None:
    report = _write_report(tmp_path / "mutation.json", {})
    rc = cli.main(
        [
            "--survivors-by-line",
            "--survivors-by-mutator",
            "--report",
            str(report),
            "--file",
            "src/calc.ts",
        ]
    )
    assert rc == 2
    err = capsys.readouterr().err
    assert (
        "exactly one of --survivors-by-line or --survivors-by-mutator" in err
    )


def test_neither_mode_flag_is_argument_error(tmp_path: Path, capsys) -> None:
    report = _write_report(tmp_path / "mutation.json", {})
    rc = cli.main(["--report", str(report), "--file", "src/calc.ts"])
    assert rc == 2
    err = capsys.readouterr().err
    assert (
        "exactly one of --survivors-by-line or --survivors-by-mutator" in err
    )


def test_skip_static_with_survivors_by_line_is_argument_error(
    tmp_path: Path, capsys
) -> None:
    report = _write_report(tmp_path / "mutation.json", {})
    rc = cli.main(
        [
            "--survivors-by-line",
            "--skip-static",
            "--report",
            str(report),
            "--file",
            "src/calc.ts",
        ]
    )
    assert rc == 2
    err = capsys.readouterr().err
    assert "--skip-static is only valid with --survivors-by-mutator" in err
