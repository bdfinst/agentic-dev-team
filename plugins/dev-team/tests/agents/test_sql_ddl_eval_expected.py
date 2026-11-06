"""The sql-ddl eval fixtures and their expected JSON agree with the catalog (#2287).

``/agent-eval`` cannot run in pytest (it needs a live model). This test pins
what is deterministic around it:

- each expected JSON names a catalog rule id and the catalog severity,
- the output a correct agent would emit passes ``validate_review_output.py``,
- the detector side of each fixture is what the expectation assumes: no hit
  on the agent-owned fixtures, and one hit on the test-setup fixture that the
  agent must dismiss.
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
INDEX = "sql.ddl.index-not-concurrent"
NARROWING = "sql.ddl.type-narrowing"
CASES = {
    "sql-ddl-type-narrowing": [],
    "sql-ddl-type-widening": [],
    "sql-ddl-index-test-setup": [INDEX],
}


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


def detector_rules(stem):
    spec = load_expected(stem)
    text = (EVALS / "fixtures" / spec["fixture"]).read_text(encoding="utf-8")
    return [h["rule"] for h in sql_scan.scan_text(text, spec["fixture"])]


def correct_output(stem):
    """What a correct sql-review emits: the expected findings, with the rule's text."""
    rules = {r.id: r for r in sql_rules.discover_rules()}
    spec = load_expected(stem)
    issues = [
        {
            "category": f["category"],
            "severity": f["severity"],
            "confidence": "medium",
            "file": spec["fixture"],
            "line": 5,
            "message": rules[f["category"]].message,
            "suggestedFix": rules[f["category"]].fix,
        }
        for f in spec["agents"]["sql-review"]["expectedFindings"]
    ]
    status = (
        "pass"
        if not issues
        else ("fail" if any(i["severity"] == "error" for i in issues) else "warn")
    )
    return {"status": status, "issues": issues, "summary": "Confidence: High"}


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
def test_correct_output_passes_the_validator_and_matches_expected(stem):
    output = correct_output(stem)
    verdict = validate_review_output.classify_and_validate(json.dumps(output))
    assert verdict["valid"] is True, verdict
    expected = load_expected(stem)["agents"]["sql-review"]
    assert output["status"] == expected["expectedStatus"]
    assert (
        expected["issueCount"]["min"]
        <= len(output["issues"])
        <= expected["issueCount"]["max"]
    )


@pytest.mark.parametrize(("stem", "hits"), CASES.items())
def test_detector_side_of_each_fixture_is_what_the_expectation_assumes(stem, hits):
    assert detector_rules(stem) == hits


def test_the_test_setup_fixture_is_dismissed_not_missed():
    """The detector hits it, yet the expected output is clean."""
    assert detector_rules("sql-ddl-index-test-setup") == [INDEX]
    expected = load_expected("sql-ddl-index-test-setup")["agents"]["sql-review"]
    assert expected["expectedFindings"] == []
    assert expected["expectedStatus"] == "pass"


def test_the_narrowing_rule_names_its_eval_fixtures():
    rule = {r.id: r for r in sql_rules.discover_rules()}[NARROWING]
    assert rule.owner == "agent"
    assert rule.positive == (load_expected("sql-ddl-type-narrowing")["fixture"],)
    assert rule.negative == (load_expected("sql-ddl-type-widening")["fixture"],)


def test_narrowing_expects_exactly_the_narrowing_error():
    expected = load_expected("sql-ddl-type-narrowing")["agents"]["sql-review"]
    assert expected["expectedFindings"] == [
        {"category": "sql.ddl.type-narrowing", "severity": "error"}
    ]
    assert expected["expectedStatus"] == "fail"
    assert "bigint" in expected["mustMention"]


def test_widening_expects_no_findings_and_a_pass():
    expected = load_expected("sql-ddl-type-widening")["agents"]["sql-review"]
    assert expected["expectedFindings"] == []
    assert expected["expectedStatus"] == "pass"


def sql_lines(name):
    text = (EVALS / "fixtures" / name).read_text(encoding="utf-8")
    return [x for x in text.splitlines() if x.strip() and not x.startswith("--")]


def test_widening_fixture_is_the_narrowing_fixture_with_the_types_swapped():
    swapped = [
        x.replace("n bigint", "n @@").replace("TYPE int", "TYPE bigint")
        for x in sql_lines("sql-ddl-type-narrowing.sql")
    ]
    swapped = [x.replace("n @@", "n int") for x in swapped]
    assert swapped == sql_lines("sql-ddl-type-widening.sql")
