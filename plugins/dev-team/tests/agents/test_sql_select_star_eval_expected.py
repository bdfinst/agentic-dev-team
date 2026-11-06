"""The select-star triage eval fixtures agree with the catalog and detector (#2284).

``/agent-eval`` needs a live model. This test pins the deterministic parts:

- the detector hits the same ``SELECT *`` in both fixtures, so the agent is
  graded on triage and not on detection,
- the keep case expects the catalog rule id and severity,
- the dismiss case expects no categorized finding,
- the output a correct agent emits for each case passes the output validator.
"""

import json
import re
import sys
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = PLUGIN_DIR.parents[1]
sys.path.insert(0, str(PLUGIN_DIR / "scripts" / "lib"))
sys.path.insert(0, str(PLUGIN_DIR / "skills" / "code-review" / "scripts"))

import sql_scan
import validate_review_output

EVALS = REPO_ROOT / "evals"
RULE = "sql.schema.select-star"
KEEP = "sql-select-star-positional"
DISMISS = "sql-select-star-named"


def load_expected(stem):
    return json.loads((EVALS / "expected" / f"{stem}.json").read_text(encoding="utf-8"))


def fixture_text(stem):
    return (EVALS / "fixtures" / load_expected(stem)["fixture"]).read_text(
        encoding="utf-8"
    )


def catalog_severity(rule_id):
    text = (PLUGIN_DIR / "knowledge" / "sql-anti-patterns" / "schema.md").read_text(
        encoding="utf-8"
    )
    section = text.split(f"### {rule_id}\n", 1)[1].split("\n### ", 1)[0]
    return re.search(r"\*\*Severity:\*\* (\S+)", section).group(1)


def agent_output(stem, keep):
    hits = sql_scan.scan_text(fixture_text(stem), f"{stem}.sql")
    issues = [
        {
            "category": h["rule"],
            "severity": h["severity"],
            "confidence": "high",
            "file": h["file"],
            "line": h["line"],
            "message": h["message"],
            "suggestedFix": h["fix"],
        }
        for h in hits
        if keep
    ]
    summary = (
        "Confirmed detector hit. Confidence: High"
        if keep
        else "Dismissed sql.schema.select-star: rows are read by column name only. Confidence: High"
    )
    return {
        "status": "warn" if issues else "pass",
        "issues": issues,
        "summary": summary,
    }


@pytest.mark.parametrize("stem", [KEEP, DISMISS])
def test_fixture_and_expected_pair_exist(stem):
    spec = load_expected(stem)
    assert (EVALS / "fixtures" / spec["fixture"]).is_file()
    assert spec["applicableAgents"] == ["sql-review"]


@pytest.mark.parametrize("stem", [KEEP, DISMISS])
def test_detector_hits_the_select_star_in_both_fixtures(stem):
    hits = sql_scan.scan_text(fixture_text(stem), f"{stem}.sql")
    assert [(h["rule"], h["line"]) for h in hits] == [(RULE, 3)]


def test_keep_case_expects_the_catalog_rule_and_severity():
    expected = load_expected(KEEP)["agents"]["sql-review"]
    assert expected["expectedFindings"] == [
        {"category": RULE, "severity": catalog_severity(RULE)}
    ]
    assert expected["expectedStatus"] == "warn"


def test_dismiss_case_expects_no_categorized_finding():
    expected = load_expected(DISMISS)["agents"]["sql-review"]
    assert expected["expectedFindings"] == []
    assert expected["expectedStatus"] == "pass"
    assert expected["issueCount"] == {"min": 0, "max": 0}


def test_fixtures_differ_only_in_how_the_rows_are_consumed():
    assert "by index" in fixture_text(KEEP)
    assert "by column name" in fixture_text(DISMISS)


@pytest.mark.parametrize(("stem", "keep"), [(KEEP, True), (DISMISS, False)])
def test_correct_output_passes_the_review_output_validator(stem, keep):
    verdict = validate_review_output.classify_and_validate(
        json.dumps(agent_output(stem, keep))
    )
    assert verdict["valid"] is True, verdict


def test_keep_output_matches_expected_findings():
    expected = load_expected(KEEP)["agents"]["sql-review"]
    want = {(f["category"], f["severity"]) for f in expected["expectedFindings"]}
    got = {(i["category"], i["severity"]) for i in agent_output(KEEP, True)["issues"]}
    assert got == want


def test_dismiss_output_names_the_dismissal_reason_in_summary():
    summary = agent_output(DISMISS, False)["summary"]
    assert RULE in summary and "column name" in summary


def test_agent_definition_describes_select_star_triage():
    agent = (PLUGIN_DIR / "agents" / "sql-review.md").read_text(encoding="utf-8")
    assert "sql.schema.select-star` triage" in agent
