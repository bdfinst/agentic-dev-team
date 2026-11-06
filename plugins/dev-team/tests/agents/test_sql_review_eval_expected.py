"""The sql-review eval fixtures and their expected JSON agree with the catalog (#2283).

``/agent-eval`` cannot run in pytest (it needs a live model). This test pins
everything around it that is deterministic:

- the expected JSON names a catalog rule id and the catalog severity,
- the output a correct agent would emit passes ``validate_review_output.py``,
- the detector produces exactly the hits the expected JSON implies, so the
  agent is graded on a fixture where the detector and the expectation agree.
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

import sql_rules
import sql_scan
import validate_review_output

EVALS = REPO_ROOT / "evals"
CATALOG = PLUGIN_DIR / "knowledge" / "sql-anti-patterns"
CASES = ["sql-positional-insert", "sql-clean", "sql-boundary-injection-loop"]
RULES = {r.id: r for r in sql_rules.discover_rules()}


def load_expected(stem):
    return json.loads((EVALS / "expected" / f"{stem}.json").read_text(encoding="utf-8"))


def catalog_severities():
    found = {}
    for path in CATALOG.glob("*.md"):
        current = None
        for line in path.read_text(encoding="utf-8").splitlines():
            heading = re.match(r"^### (sql\.\S+)$", line)
            if heading:
                current = heading.group(1)
            severity = re.match(r"^- \*\*Severity:\*\* (\S+)$", line)
            if severity and current:
                found[current] = severity.group(1)
    return found


def agent_output_for(stem):
    """What a correct sql-review emits for the fixture: confirmed detector hits."""
    spec = load_expected(stem)
    fixture = EVALS / "fixtures" / spec["fixture"]
    if fixture.suffix == ".sql":
        hits = sql_scan.scan_text(fixture.read_text(encoding="utf-8"), spec["fixture"])
    else:  # embedded SQL: the detector extracts the literals first
        hits = sql_scan.scan_paths([str(fixture)]).findings
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
    ]
    status = (
        "pass"
        if not issues
        else ("fail" if any(i["severity"] == "error" for i in issues) else "warn")
    )
    return {
        "status": status,
        "issues": issues,
        "summary": "Confirmed detector hits. Confidence: High",
    }


@pytest.mark.parametrize("stem", CASES)
def test_fixture_and_expected_pair_exist(stem):
    spec = load_expected(stem)
    assert (EVALS / "fixtures" / spec["fixture"]).is_file()
    assert spec["applicableAgents"] == ["sql-review"]
    assert set(spec["agents"]) == {"sql-review"}


@pytest.mark.parametrize("stem", CASES)
def test_expected_findings_use_catalog_ids_and_severities(stem):
    severities = catalog_severities()
    for finding in load_expected(stem)["agents"]["sql-review"]["expectedFindings"]:
        assert finding["category"] in severities
        assert finding["severity"] == severities[finding["category"]]


@pytest.mark.parametrize("stem", CASES)
def test_expected_findings_match_the_detector_hits(stem):
    expected = load_expected(stem)["agents"]["sql-review"]
    want = {(f["category"], f["severity"]) for f in expected["expectedFindings"]}
    got = {(i["category"], i["severity"]) for i in agent_output_for(stem)["issues"]}
    assert got == want


@pytest.mark.parametrize("stem", CASES)
def test_correct_output_passes_the_review_output_validator(stem):
    verdict = validate_review_output.classify_and_validate(
        json.dumps(agent_output_for(stem))
    )
    assert verdict["valid"] is True, verdict


@pytest.mark.parametrize("stem", CASES)
def test_correct_output_status_and_counts_match_expected(stem):
    expected = load_expected(stem)["agents"]["sql-review"]
    output = agent_output_for(stem)
    assert output["status"] == expected["expectedStatus"]
    assert (
        expected["issueCount"]["min"]
        <= len(output["issues"])
        <= expected["issueCount"]["max"]
    )


def test_positive_fixture_hit_is_on_the_positional_line():
    issues = agent_output_for("sql-positional-insert")["issues"]
    assert [(i["category"], i["line"]) for i in issues] == [
        ("sql.schema.positional-insert", 3)
    ]


def test_every_issue_carries_a_one_line_message_and_fix_from_the_rule():
    for stem in CASES:
        for issue in agent_output_for(stem)["issues"]:
            rule = RULES[issue["category"]]
            assert issue["message"] == rule.message
            assert issue["suggestedFix"] == rule.fix
            assert "\n" not in issue["message"] + issue["suggestedFix"]


def test_fixtures_are_sql_files_or_embedded_source():
    suffixes = {Path(load_expected(stem)["fixture"]).suffix for stem in CASES}
    assert suffixes == {".sql", ".py"}


def test_boundary_fixture_has_embedded_sql_but_no_issues():
    """Vacuity guard: the clean verdict comes from scanned SQL, not an empty scan."""
    fixture = (
        EVALS / "fixtures" / load_expected("sql-boundary-injection-loop")["fixture"]
    )
    result = sql_scan.scan_paths([str(fixture)])
    assert result.dispatch is True
    assert result.skipped_fragments
    assert agent_output_for("sql-boundary-injection-loop")["issues"] == []
