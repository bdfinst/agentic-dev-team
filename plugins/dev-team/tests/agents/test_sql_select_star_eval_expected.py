"""The select-star triage eval fixtures agree with the catalog and detector (#2284).

``/agent-eval`` needs a live model. This test pins the deterministic parts:

- the detector hits the same ``SELECT *`` in both fixtures, and the two
  fixtures differ only in the comment that says how the rows are consumed,
  so the agent is graded on triage and not on detection,
- the keep case expects the catalog rule id and severity,
- the dismiss case expects no categorized finding,
- the agent definition carries the keep and dismiss criteria the fixtures test.
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
AGENT = PLUGIN_DIR / "agents" / "sql-review.md"
RULE = "sql.schema.select-star"
KEEP = "sql-select-star-positional"
DISMISS = "sql-select-star-named"


def load_expected(stem):
    return json.loads((EVALS / "expected" / f"{stem}.json").read_text(encoding="utf-8"))


def fixture_text(stem):
    return (EVALS / "fixtures" / load_expected(stem)["fixture"]).read_text(
        encoding="utf-8"
    )


def code_only(text):
    """The fixture without its ``--`` comment lines."""
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("--")
    )


def catalog_severity(rule_id):
    text = (PLUGIN_DIR / "knowledge" / "sql-anti-patterns" / "schema.md").read_text(
        encoding="utf-8"
    )
    section = text.split(f"### {rule_id}\n", 1)[1].split("\n### ", 1)[0]
    return re.search(r"\*\*Severity:\*\* (\S+)", section).group(1)


def hits_for(stem):
    return sql_scan.scan_text(fixture_text(stem), f"{stem}.sql")


def issue_from_hit(hit):
    """The issue a confirming agent emits for one detector hit."""
    return {
        "category": hit["rule"],
        "severity": hit["severity"],
        "confidence": "high",
        "file": hit["file"],
        "line": hit["line"],
        "message": hit["message"],
        "suggestedFix": hit["fix"],
    }


def triage_section():
    text = AGENT.read_text(encoding="utf-8")
    start = text.index(f"- **`{RULE}` triage.**")
    end = text.index("- **Agent-owned rules.**", start)
    return " ".join(text[start:end].split())


@pytest.mark.parametrize("stem", [KEEP, DISMISS])
def test_fixture_and_expected_pair_exist(stem):
    spec = load_expected(stem)
    assert (EVALS / "fixtures" / spec["fixture"]).is_file()
    assert spec["applicableAgents"] == ["sql-review"]


@pytest.mark.parametrize("stem", [KEEP, DISMISS])
def test_detector_hits_the_select_star_in_both_fixtures(stem):
    assert [(h["rule"], h["line"]) for h in hits_for(stem)] == [(RULE, 3)]


def test_fixtures_differ_only_in_how_the_rows_are_consumed():
    assert code_only(fixture_text(KEEP)) == code_only(fixture_text(DISMISS))
    assert fixture_text(KEEP) != fixture_text(DISMISS)


def test_keep_case_hit_becomes_a_valid_issue_matching_expected_findings():
    expected = load_expected(KEEP)["agents"]["sql-review"]
    assert expected["expectedFindings"] == [
        {"category": RULE, "severity": catalog_severity(RULE)}
    ]
    assert expected["expectedStatus"] == "warn"
    issues = [issue_from_hit(h) for h in hits_for(KEEP)]
    assert {(i["category"], i["severity"]) for i in issues} == {
        (f["category"], f["severity"]) for f in expected["expectedFindings"]
    }
    output = {"status": "warn", "issues": issues, "summary": "Kept. Confidence: High"}
    verdict = validate_review_output.classify_and_validate(json.dumps(output))
    assert verdict["valid"] is True, verdict


def test_dismiss_case_expects_no_categorized_finding_and_a_valid_pass():
    expected = load_expected(DISMISS)["agents"]["sql-review"]
    assert expected["expectedFindings"] == []
    assert expected["expectedStatus"] == "pass"
    assert expected["issueCount"] == {"min": 0, "max": 0}
    output = {"status": "pass", "issues": [], "summary": "Dismissed. Confidence: High"}
    verdict = validate_review_output.classify_and_validate(json.dumps(output))
    assert verdict["valid"] is True, verdict


@pytest.mark.parametrize(
    "criterion",
    [
        "row index",
        "tuple unpacking",
        "positional binding",
        "defines a view",
        "named columns only",
        "name that consumer in `summary`",
    ],
)
def test_agent_triage_section_carries_keep_and_dismiss_criteria(criterion):
    assert criterion in triage_section()
