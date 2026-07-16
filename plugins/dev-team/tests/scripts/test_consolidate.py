"""Unit tests for skills/code-review/scripts/consolidate.py.

Covers the pure consolidate(): cross-slice file:line dedup with agent merge and
highest-severity, single-slice pass-through, recurring-theme rollup (>=2 slices),
declarative-panel disclosure, overall status, empty input; plus main()'s
malformed-artifact reporting.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(
    0,
    str(_REPO_ROOT / "plugins" / "dev-team" / "skills" / "code-review" / "scripts"),
)

import consolidate  # noqa: E402


def _section(sid, findings, is_declarative=False, panel=None):
    return {
        "schema": "code-review-section/v1",
        "id": sid,
        "files": [f"src/{sid}.ts"],
        "is_declarative": is_declarative,
        "panel": panel or ["correctness-review", "structure-review"],
        "findings": findings,
    }


def _f(file, line, severity, agent, message="msg"):
    return {"file": file, "line": line, "severity": severity, "agent": agent, "message": message}


def test_cross_slice_duplicate_merges_to_one_entry():
    sections = [
        _section("0001", [_f("src/a.ts", 10, "warning", "structure-review")]),
        _section("0002", [_f("src/a.ts", 10, "error", "complexity-review")]),
    ]
    result = consolidate.consolidate(sections)
    assert len(result["topFindings"]) == 1
    entry = result["topFindings"][0]
    assert entry["file"] == "src/a.ts" and entry["line"] == 10
    # Highest severity wins; both agents merged.
    assert entry["severity"] == "error"
    assert sorted(entry["agents"]) == ["complexity-review", "structure-review"]


def test_distinct_findings_pass_through():
    sections = [
        _section("0001", [_f("src/a.ts", 1, "warning", "naming-review")]),
        _section("0002", [_f("src/b.ts", 2, "suggestion", "naming-review")]),
    ]
    result = consolidate.consolidate(sections)
    assert len(result["topFindings"]) == 2


def test_recurring_theme_fires_across_two_slices():
    sections = [
        _section("0001", [_f("src/a.ts", 1, "warning", "structure-review")]),
        _section("0002", [_f("src/b.ts", 2, "warning", "structure-review")]),
    ]
    result = consolidate.consolidate(sections)
    themes = {t["agent"]: t for t in result["recurringThemes"]}
    assert "structure-review" in themes
    assert themes["structure-review"]["slices"] == ["0001", "0002"]
    assert themes["structure-review"]["occurrences"] == 2


def test_single_slice_category_is_not_a_theme():
    sections = [
        _section("0001", [
            _f("src/a.ts", 1, "warning", "structure-review"),
            _f("src/a.ts", 2, "warning", "structure-review"),
        ]),
    ]
    result = consolidate.consolidate(sections)
    # Recurs within one slice only -> not a cross-slice theme.
    assert result["recurringThemes"] == []


def test_empty_input_is_well_formed_empty_aggregate():
    result = consolidate.consolidate([])
    assert result["sliceCount"] == 0
    assert result["topFindings"] == []
    assert result["recurringThemes"] == []
    assert result["overall"] == "pass"
    assert result["totals"] == {"errors": 0, "warnings": 0, "suggestions": 0}


def test_reduced_panel_slices_disclosed():
    sections = [
        _section("0001", [], is_declarative=True, panel=["correctness-review", "structure-review"]),
        _section("0002", [], is_declarative=False),
    ]
    result = consolidate.consolidate(sections)
    assert result["reducedPanelSlices"] == ["0001"]


def test_overall_status_reflects_highest_severity():
    assert consolidate.consolidate([_section("0001", [_f("a", 1, "error", "x")])])["overall"] == "fail"
    assert consolidate.consolidate([_section("0001", [_f("a", 1, "warning", "x")])])["overall"] == "warn"
    assert consolidate.consolidate([_section("0001", [_f("a", 1, "suggestion", "x")])])["overall"] == "pass"


def test_main_reports_malformed_artifact_not_silently_dropped(tmp_path, capsys):
    raw = tmp_path / "DEV_TEAM_REPORTS" / "code-review" / "raw"
    raw.mkdir(parents=True)
    (raw / "section-0001.json").write_text(json.dumps(_section("0001", [_f("a", 1, "warning", "x")])))
    (raw / "section-0002.json").write_text("{ this is not valid json")
    rc = consolidate.main(["--root", str(tmp_path)])
    captured = capsys.readouterr()
    # Malformed artifact reported by name to stderr, non-zero exit, valid one still consolidated.
    assert rc == 2
    assert "section-0002.json" in captured.err
    out = json.loads(captured.out)
    assert out["sliceCount"] == 1
    assert out["malformedArtifacts"]


def test_main_treats_wrong_shape_json_as_malformed(tmp_path, capsys):
    raw = tmp_path / "DEV_TEAM_REPORTS" / "code-review" / "raw"
    raw.mkdir(parents=True)
    (raw / "section-0001.json").write_text(json.dumps(_section("0001", [])))
    # Valid JSON, wrong shape (a list) — must be reported, not crash consolidate().
    (raw / "section-0002.json").write_text("[]")
    rc = consolidate.main(["--root", str(tmp_path)])
    captured = capsys.readouterr()
    assert rc == 2
    assert "section-0002.json" in captured.err
    out = json.loads(captured.out)
    assert out["sliceCount"] == 1
