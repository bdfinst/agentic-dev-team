"""Unit tests for scripts/gherkin_failure_path_gate.py (issue #1420).

Covers the failure-path coverage gate: keyword matching against scenario
titles + step text, directory scanning, the main() CLI's exit-code contract,
and the accepted false-positive limitation of the keyword heuristic.
"""

from __future__ import annotations

import json
import sys

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "scripts"))

import gherkin_failure_path_gate as gate

HAPPY_ONLY = """Feature: Orders API

  Scenario: Create order succeeds
    Given a valid payload
    When the order is created
    Then the response status is 201
"""

HAPPY_AND_FAILURE = (
    HAPPY_ONLY
    + """
  Scenario: Create order fails when payload is missing required field
    Given a payload missing a required field
    When the order is created
    Then the response status is 400
"""
)

RETRY_POLICY = """Feature: Retry Policy

  Scenario: Retry succeeds and does not exceed the configured limit
    Given a retryable operation
    When it retries within the configured limit
    Then the operation eventually succeeds
"""


def test_feature_with_only_happy_path_is_flagged():
    features = gate.parse_features(HAPPY_ONLY)
    for f in features:
        f["file"] = "orders.feature"
    findings = gate.find_missing_failure_path(features, gate.DEFAULT_KEYWORDS)
    assert len(findings) == 1
    assert findings[0]["feature_title"] == "Orders API"
    assert findings[0]["line"] == 1


def test_feature_with_a_failure_path_scenario_passes():
    features = gate.parse_features(HAPPY_AND_FAILURE)
    for f in features:
        f["file"] = "orders.feature"
    findings = gate.find_missing_failure_path(features, gate.DEFAULT_KEYWORDS)
    assert findings == []


def test_file_with_no_feature_header_yields_no_findings_no_crash(tmp_path):
    f = tmp_path / "empty.feature"
    f.write_text("# just a comment\n")
    features = gate.parse_features(f.read_text())
    assert features == []


def test_two_feature_blocks_in_one_file_evaluated_independently():
    text = HAPPY_ONLY + "\n" + HAPPY_AND_FAILURE.replace("Orders API", "Refunds API")
    features = gate.parse_features(text)
    assert len(features) == 2
    for f in features:
        f["file"] = "combined.feature"
    findings = gate.find_missing_failure_path(features, gate.DEFAULT_KEYWORDS)
    assert len(findings) == 1
    assert findings[0]["feature_title"] == "Orders API"


def test_retry_scenario_with_no_default_keyword_substring_is_correctly_flagged():
    """The default keyword list has no substring in common with "does not
    exceed the configured limit" ("exceeds" != "exceed"), so this
    happy-path-only Feature is correctly flagged as missing a failure path.
    """
    features = gate.parse_features(RETRY_POLICY)
    for f in features:
        f["file"] = "retry.feature"
    findings = gate.find_missing_failure_path(features, gate.DEFAULT_KEYWORDS)
    assert len(findings) == 1


def test_extra_keyword_can_produce_a_documented_false_positive():
    """The keyword heuristic's accepted limitation, demonstrated: adding
    "exceed" via --extra-keyword makes this happy-path-only scenario pass
    the gate, because "exceed" happens to be a substring of its text — even
    though it has no real failure path. This is the documented heuristic
    limitation (Risks & Open Questions), not correct classification.
    """
    features = gate.parse_features(RETRY_POLICY)
    for f in features:
        f["file"] = "retry.feature"
    keywords = list(gate.DEFAULT_KEYWORDS) + ["exceed"]
    findings = gate.find_missing_failure_path(features, keywords)
    assert findings == []  # false positive: no real failure-path scenario exists


def test_keyword_override_replaces_default_list_entirely(tmp_path):
    findings = gate.find_missing_failure_path(
        [{"file": "x", "line": 1, "title": "X", "scenario_titles": ["Create order succeeds"], "scenario_text": HAPPY_ONLY}],
        ["succeeds"],
    )
    assert findings == []


def test_main_json_output_contract(tmp_path):
    (tmp_path / "orders.feature").write_text(HAPPY_ONLY)
    exit_code = gate.main(["--dir", str(tmp_path), "--json"])
    assert exit_code == 1


def test_main_exits_zero_when_all_features_have_failure_path(tmp_path, capsys):
    (tmp_path / "orders.feature").write_text(HAPPY_AND_FAILURE)
    exit_code = gate.main(["--dir", str(tmp_path)])
    assert exit_code == 0
    assert "OK" in capsys.readouterr().out


def test_main_names_file_and_line_for_findings(tmp_path, capsys):
    (tmp_path / "orders.feature").write_text(HAPPY_ONLY)
    exit_code = gate.main(["--dir", str(tmp_path)])
    assert exit_code == 1
    out = capsys.readouterr().out
    assert "orders.feature:1" in out
    assert "Orders API" in out
