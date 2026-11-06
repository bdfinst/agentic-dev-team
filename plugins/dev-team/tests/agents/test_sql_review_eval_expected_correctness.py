"""Eval fixtures for the correctness and index rules agree with the catalog (#2286).

``/agent-eval`` needs a live model and cannot run in pytest. This test pins the
deterministic parts around it, for the six ``sql-correctness-*`` and
``sql-index-*`` fixtures:

- each expected JSON names catalog rule ids at the catalog severity,
- the detector hits on the fixture equal the expected script-owned findings,
  plus the hits the agent must dismiss (``DISMISSED``), so the agent is graded
  on a fixture where the detector and the expectation agree,
- agent-owned rules fire nowhere in the detector,
- the output a correct agent emits validates, and its status and counts match,
- the registry points each agent-owned rule at fixtures that exist, and the
  positive and negative ones carry the expected finding and no finding.
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
AGENT = PLUGIN_DIR / "agents" / "sql-review.md"

NOT_IN = "sql.correctness.not-in-subquery"
DISTINCT = "sql.correctness.distinct-masks-join"
CONVERSION = "sql.index.implicit-conversion"

CASES = [
    "sql-correctness-not-in-nullable",
    "sql-correctness-not-in-not-null",
    "sql-correctness-distinct-join",
    "sql-correctness-distinct-single",
    "sql-index-implicit-conversion",
    "sql-index-int-compare",
]
# Detector hits the agent must dismiss on a fixture.
DISMISSED = {"sql-correctness-not-in-not-null": {NOT_IN}}
# The text on the line where the agent reports its own finding.
AGENT_MARKERS = {DISTINCT: "DISTINCT", CONVERSION: "= 42"}
# Findings only the agent can make.
AGENT_FINDINGS = {
    "sql-correctness-distinct-join": {DISTINCT},
    "sql-index-implicit-conversion": {CONVERSION},
}
RULES = {r.id: r for r in sql_rules.discover_rules()}


def load_expected(stem):
    return json.loads((EVALS / "expected" / f"{stem}.json").read_text(encoding="utf-8"))


def expected_pairs(stem):
    spec = load_expected(stem)["agents"]["sql-review"]
    return {(f["category"], f["severity"]) for f in spec["expectedFindings"]}


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


def detector_hits(stem):
    spec = load_expected(stem)
    text = (EVALS / "fixtures" / spec["fixture"]).read_text(encoding="utf-8")
    return sql_scan.scan_text(text, spec["fixture"])


def fixture_line(stem, marker):
    """1-based line of the first fixture line that holds ``marker``."""
    text = (EVALS / "fixtures" / load_expected(stem)["fixture"]).read_text()
    for number, line in enumerate(text.splitlines(), start=1):
        if marker in line:
            return number
    raise AssertionError(f"{marker!r} not in {stem}")


def agent_output_for(stem):
    """What a correct sql-review emits: detector hits minus dismissals, plus its own."""
    issues = []
    for hit in detector_hits(stem):
        if hit["rule"] in DISMISSED.get(stem, set()):
            continue
        issues.append(
            {
                "category": hit["rule"],
                "severity": hit["severity"],
                "confidence": "high",
                "file": hit["file"],
                "line": hit["line"],
                "message": hit["message"],
                "suggestedFix": hit["fix"],
            }
        )
    for rule_id in AGENT_FINDINGS.get(stem, set()):
        rule = RULES[rule_id]
        issues.append(
            {
                "category": rule.id,
                "severity": rule.severity,
                "confidence": "medium",
                "file": load_expected(stem)["fixture"],
                "line": fixture_line(stem, AGENT_MARKERS[rule_id]),
                "message": rule.message,
                "suggestedFix": rule.fix,
            }
        )
    status = (
        "pass"
        if not issues
        else ("fail" if any(i["severity"] == "error" for i in issues) else "warn")
    )
    return {
        "status": status,
        "issues": issues,
        "summary": "Confirmed findings. Confidence: High",
    }


@pytest.mark.parametrize("stem", CASES)
def test_fixture_and_expected_pair_exist(stem):
    spec = load_expected(stem)
    assert (EVALS / "fixtures" / spec["fixture"]).is_file()
    assert spec["fixture"] == f"{stem}.sql"
    assert spec["applicableAgents"] == ["sql-review"]
    assert set(spec["agents"]) == {"sql-review"}


@pytest.mark.parametrize("stem", CASES)
def test_expected_findings_use_catalog_ids_and_severities(stem):
    severities = catalog_severities()
    for category, severity in expected_pairs(stem):
        assert category in severities
        assert severity == severities[category]


@pytest.mark.parametrize("stem", CASES)
def test_detector_hits_equal_expected_script_findings_plus_dismissals(stem):
    hits = {h["rule"] for h in detector_hits(stem)}
    scripted = {
        c for c, _ in expected_pairs(stem) if RULES[c].owner == sql_rules.OWNER_SCRIPT
    }
    assert hits == scripted | DISMISSED.get(stem, set())


@pytest.mark.parametrize("stem", CASES)
def test_correct_output_matches_expected_findings(stem):
    got = {(i["category"], i["severity"]) for i in agent_output_for(stem)["issues"]}
    assert got == expected_pairs(stem)


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


def test_nullable_and_not_null_fixtures_differ_only_in_the_column_nullability():
    nullable = (EVALS / "fixtures" / "sql-correctness-not-in-nullable.sql").read_text()
    not_null = (EVALS / "fixtures" / "sql-correctness-not-in-not-null.sql").read_text()
    assert nullable.replace("t_id int NULL", "t_id int NOT NULL") == not_null


@pytest.mark.parametrize(
    ("rule_id", "positive", "negative"),
    [
        (DISTINCT, "sql-correctness-distinct-join", "sql-correctness-distinct-single"),
        (CONVERSION, "sql-index-implicit-conversion", "sql-index-int-compare"),
    ],
)
def test_agent_owned_rules_point_at_their_positive_and_negative_fixtures(
    rule_id, positive, negative
):
    rule = RULES[rule_id]
    assert rule.positive == (f"{positive}.sql",)
    assert rule.negative == (f"{negative}.sql",)
    assert (rule_id, rule.severity) in expected_pairs(positive)
    assert expected_pairs(negative) == set()


def agent_bullet(marker):
    """Text of the top-level bullet in sql-review.md that holds ``marker``."""
    lines = AGENT.read_text(encoding="utf-8").splitlines()
    first = next(i for i, l in enumerate(lines) if l.startswith("- **") and marker in l)
    last = first + 1
    while last < len(lines) and not lines[last].startswith(("- **", "#")):
        last += 1
    return " ".join(" ".join(lines[first:last]).split())


@pytest.mark.parametrize("rule_id", [DISTINCT, CONVERSION])
def test_agent_owned_bullet_names_the_rule(rule_id):
    assert rule_id in agent_bullet("Agent-owned rules")


def test_not_in_triage_keeps_nullable_and_dismisses_not_null():
    bullet = agent_bullet("Triage `sql.correctness.not-in-subquery`")
    assert re.search(r"Keep[^.]*nullable", bullet)
    assert re.search(r"Dismiss[^.]*NOT NULL", bullet)


@pytest.mark.parametrize("stem", CASES)
def test_must_mention_terms_appear_in_the_issue_messages(stem):
    """The grader reads messages, so a contract-compliant agent must be able to hit them."""
    spec = load_expected(stem)["agents"]["sql-review"]
    messages = " ".join(i["message"] for i in agent_output_for(stem)["issues"])
    for term in spec.get("mustMention", []):
        assert term.lower() in messages.lower(), term


@pytest.mark.parametrize("stem", CASES)
def test_severity_ranges_hold_for_the_synthesized_issues(stem):
    spec = load_expected(stem)["agents"]["sql-review"]
    issues = agent_output_for(stem)["issues"]
    for severity, bounds in spec.get("severities", {}).items():
        found = sum(1 for i in issues if i["severity"] == severity)
        assert bounds["min"] <= found <= bounds["max"], severity
