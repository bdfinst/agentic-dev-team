"""Unit tests for skills/code-review/scripts/consolidate.py.

Covers the pure consolidate(): cross-slice file:line dedup with agent merge and
highest-severity, single-slice pass-through, recurring-theme rollup (>=2 slices),
declarative-panel disclosure, overall status, empty input; plus main()'s
malformed-artifact reporting.
"""

from __future__ import annotations

import json
import sys

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(
    0,
    str(_REPO_ROOT / "plugins" / "dev-team" / "skills" / "code-review" / "scripts"),
)

import consolidate


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


# --- schema-drift tolerance (#1261) -------------------------------------------


def test_section_findings_under_issues_key_are_aggregated():
    """A section whose findings landed under `issues` (per-agent key) instead of
    `findings` (section key) is still aggregated — not silently counted as zero."""
    section = {
        "schema": "code-review-section/v1",
        "id": "0001",
        "files": ["src/a.ts"],
        "is_declarative": False,
        "panel": ["structure-review"],
        "issues": [_f("src/a.ts", 10, "error", "structure-review")],
    }
    result = consolidate.consolidate([section])
    assert result["totals"]["errors"] == 1
    assert len(result["topFindings"]) == 1
    assert result["topFindings"][0]["agents"] == ["structure-review"]


def test_findings_key_wins_when_both_present():
    section = _section("0001", [_f("src/a.ts", 1, "warning", "x")])
    section["issues"] = [_f("src/b.ts", 2, "error", "y")]
    result = consolidate.consolidate([section])
    # `findings` is canonical and takes precedence over the `issues` alias.
    assert [f["file"] for f in result["topFindings"]] == ["src/a.ts"]


def test_non_list_findings_value_degrades_to_empty():
    section = _section("0001", [])
    section["findings"] = "oops"  # wrong type, not a list
    section["issues"] = [_f("src/a.ts", 1, "warning", "x")]
    # `findings` present-but-not-a-list falls through to the `issues` alias.
    result = consolidate.consolidate([section])
    assert result["totals"]["warnings"] == 1


def test_normalize_native_agent_shape_with_extra_keys():
    """Native per-agent {status, issues, summary} shape → agent-tagged findings."""
    raw = {
        "agentName": "security-review",
        "status": "fail",
        "summary": "1 issue",
        "issues": [{"severity": "error", "file": "src/x.ts", "line": 5, "message": "sqli"}],
    }
    findings = consolidate.normalize_agent_result(raw)
    assert len(findings) == 1
    assert findings[0]["agent"] == "security-review"
    assert findings[0]["severity"] == "error"


def test_normalize_findings_key_variant_and_fallback_agent_name():
    raw = {"status": "warn", "findings": [{"severity": "warning", "file": "a", "line": 1}]}
    findings = consolidate.normalize_agent_result(raw, agent_name="naming-review")
    # No agentName in payload → fall back to the passed agent_name.
    assert findings[0]["agent"] == "naming-review"


def test_normalize_preserves_explicit_agent_over_fallback():
    raw = {"issues": [{"severity": "error", "file": "a", "line": 1, "agent": "js-fp-review"}]}
    findings = consolidate.normalize_agent_result(raw, agent_name="naming-review")
    # A finding that already names its agent keeps it (setdefault, not overwrite).
    assert findings[0]["agent"] == "js-fp-review"


def test_normalize_malformed_inputs_never_raise():
    assert consolidate.normalize_agent_result(None) == []
    assert consolidate.normalize_agent_result("not-a-dict") == []
    assert consolidate.normalize_agent_result({}) == []
    # A non-dict entry inside the findings list is skipped, not crashed on.
    assert consolidate.normalize_agent_result({"issues": ["bogus", {"file": "a"}]}) == [
        {"file": "a", "agent": None}
    ]


def test_normalized_findings_feed_consolidate_end_to_end():
    """The normalize→section→consolidate path an orchestrator would follow."""
    agent_a = {"agentName": "structure-review", "status": "warn",
               "issues": [{"severity": "warning", "file": "src/a.ts", "line": 10, "message": "m"}]}
    agent_b = {"agentName": "complexity-review", "status": "fail",
               "findings": [{"severity": "error", "file": "src/a.ts", "line": 10, "message": "m"}]}
    findings = consolidate.normalize_agent_result(agent_a) + consolidate.normalize_agent_result(agent_b)
    result = consolidate.consolidate([_section("0001", findings)])
    entry = result["topFindings"][0]
    assert entry["severity"] == "error"
    assert sorted(entry["agents"]) == ["complexity-review", "structure-review"]
