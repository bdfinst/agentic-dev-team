"""Unit tests for scripts/gherkin_cross_feature_duplicate_titles_gate.py
(issue #1526).

Covers cross-Feature scenario-title collision detection, the main() CLI's
exit-code contract, and the explicit out-of-scope carve-out for a title
repeated within the *same* Feature block (that's gherkin_feature_merge.py's
own merge-dedup concern, not this gate's).
"""

from __future__ import annotations

import json
import sys

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "scripts"))

import gherkin_cross_feature_duplicate_titles_gate as gate

ORDERS_FEATURE = """Feature: POST /orders

  Scenario: returns error for invalid input
    Given an invalid payload
    When the order is created
    Then the response status is 400
"""

USERS_FEATURE = """Feature: POST /users

  Scenario: returns error for invalid input
    Given an invalid payload
    When the user is created
    Then the response status is 400
"""

REFUNDS_FEATURE = """Feature: POST /refunds

  Scenario: returns the created refund with a 201
    Given a valid payload
    When the refund is created
    Then the response status is 201
"""


def test_same_title_across_two_distinct_features_is_flagged():
    entries = gate.parse_scenario_locations(ORDERS_FEATURE, "orders.feature")
    entries += gate.parse_scenario_locations(USERS_FEATURE, "users.feature")
    findings = gate.find_cross_feature_duplicates(entries)
    assert len(findings) == 1
    assert findings[0]["scenario_title"] == "returns error for invalid input"
    feature_titles = {o["feature_title"] for o in findings[0]["occurrences"]}
    assert feature_titles == {"POST /orders", "POST /users"}


def test_distinct_titles_across_features_produce_no_findings():
    entries = gate.parse_scenario_locations(ORDERS_FEATURE, "orders.feature")
    entries += gate.parse_scenario_locations(REFUNDS_FEATURE, "refunds.feature")
    findings = gate.find_cross_feature_duplicates(entries)
    assert findings == []


def test_title_repeated_within_the_same_feature_is_not_flagged():
    """Out of scope by design: a title repeated under the *same* Feature
    title is gherkin_feature_merge.py's own within-file merge-dedup concern
    (issue #1420), not this gate's."""
    doubled = """Feature: POST /orders

  Scenario: returns error for invalid input
    Given an invalid payload
    When the order is created
    Then the response status is 400

  Scenario: returns error for invalid input
    Given a different invalid payload
    When the order is created
    Then the response status is 400
"""
    entries = gate.parse_scenario_locations(doubled, "orders.feature")
    assert len(entries) == 2
    findings = gate.find_cross_feature_duplicates(entries)
    assert findings == []


def test_parse_scenario_locations_records_each_scenarios_own_line():
    entries = gate.parse_scenario_locations(ORDERS_FEATURE, "orders.feature")
    assert len(entries) == 1
    assert entries[0]["feature_title"] == "POST /orders"
    assert entries[0]["scenario_title"] == "returns error for invalid input"
    assert entries[0]["line"] == 3


def test_scenario_outline_titles_are_included():
    text = """Feature: GET /widgets

  Scenario Outline: returns error for invalid input
    Given a <bad> payload
    Then the response status is 400

    Examples:
      | bad |
      | x   |
"""
    entries = gate.parse_scenario_locations(text, "widgets.feature")
    assert len(entries) == 1
    assert entries[0]["scenario_title"] == "returns error for invalid input"


def test_tag_on_a_following_feature_block_does_not_leak_into_this_blocks_scenarios():
    text = ORDERS_FEATURE + "\n@error-handling\n" + USERS_FEATURE
    entries = gate.parse_scenario_locations(text, "combined.feature")
    assert len(entries) == 2
    assert {e["feature_title"] for e in entries} == {"POST /orders", "POST /users"}


def test_main_json_output_contract(tmp_path, capsys):
    (tmp_path / "orders.feature").write_text(ORDERS_FEATURE)
    (tmp_path / "users.feature").write_text(USERS_FEATURE)
    exit_code = gate.main(["--dir", str(tmp_path), "--json"])
    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {"scanned", "findings"}
    assert len(payload["findings"]) == 1
    finding = payload["findings"][0]
    assert finding["scenario_title"] == "returns error for invalid input"
    assert len(finding["occurrences"]) == 2
    for occurrence in finding["occurrences"]:
        assert set(occurrence) == {"feature_title", "file", "line"}


def test_main_names_titles_and_locations_for_findings(tmp_path, capsys):
    (tmp_path / "orders.feature").write_text(ORDERS_FEATURE)
    (tmp_path / "users.feature").write_text(USERS_FEATURE)
    exit_code = gate.main(["--dir", str(tmp_path)])
    assert exit_code == 1
    out = capsys.readouterr().out
    assert "returns error for invalid input" in out
    assert "POST /orders" in out
    assert "POST /users" in out
    assert "orders.feature:3" in out
    assert "users.feature:3" in out


def test_main_exits_zero_when_no_titles_collide(tmp_path, capsys):
    (tmp_path / "orders.feature").write_text(ORDERS_FEATURE)
    (tmp_path / "refunds.feature").write_text(REFUNDS_FEATURE)
    exit_code = gate.main(["--dir", str(tmp_path)])
    assert exit_code == 0
    assert "OK" in capsys.readouterr().out


def test_main_does_not_silently_pass_when_dir_does_not_exist(tmp_path, capsys):
    missing_dir = tmp_path / "does-not-exist"
    exit_code = gate.main(["--dir", str(missing_dir)])
    assert exit_code == 2
    out = capsys.readouterr().out
    assert "OK" not in out
    assert "no .feature files found" in out


def test_main_json_warns_when_dir_does_not_exist(tmp_path, capsys):
    missing_dir = tmp_path / "does-not-exist"
    exit_code = gate.main(["--dir", str(missing_dir), "--json"])
    assert exit_code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["scanned"] == []
    assert payload["findings"] == []
    assert "no .feature files found" in payload["warning"]


def test_main_strips_control_characters_from_scenario_title_in_text_output(tmp_path, capsys):
    """CWE-150: a title is untrusted (drawn from whatever repo is being
    scanned) and must not be able to inject terminal escape sequences into
    the gate's own report."""
    hostile_title = "returns error for invalid input\x1b[31m"
    orders = f"""Feature: POST /orders

  Scenario: {hostile_title}
    Given an invalid payload
    Then the response status is 400
"""
    users = f"""Feature: POST /users

  Scenario: {hostile_title}
    Given an invalid payload
    Then the response status is 400
"""
    (tmp_path / "orders.feature").write_text(orders)
    (tmp_path / "users.feature").write_text(users)
    exit_code = gate.main(["--dir", str(tmp_path)])
    assert exit_code == 1
    out = capsys.readouterr().out
    assert "\x1b" not in out
    assert "returns error for invalid input" in out


@pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason="NTFS rejects raw control-byte filenames; POSIX-only fixture",
)
def test_main_strips_control_characters_from_file_path_in_text_output(tmp_path, capsys):
    """The scanned file's path is drawn from the same untrusted repository as
    scenario/feature titles — a crafted filename must not bypass the same
    CWE-150 guard applied to title text right next to it in the report."""
    hostile_name = "orders\x1b[31m.feature"
    (tmp_path / hostile_name).write_text(ORDERS_FEATURE)
    (tmp_path / "users.feature").write_text(USERS_FEATURE)
    exit_code = gate.main(["--dir", str(tmp_path)])
    assert exit_code == 1
    out = capsys.readouterr().out
    assert "\x1b" not in out


def test_main_strips_control_characters_from_feature_title_in_text_output(tmp_path, capsys):
    """The Feature: title guard is a separate _safe_for_terminal call site
    from the scenario title and file path guards — each needs its own
    hostile-input coverage, or reverting just this one call would leave the
    whole suite green."""
    orders = """Feature: POST /orders\x1b[31m

  Scenario: returns error for invalid input
    Given an invalid payload
    Then the response status is 400
"""
    users = """Feature: POST /users\x1b[31m

  Scenario: returns error for invalid input
    Given an invalid payload
    Then the response status is 400
"""
    (tmp_path / "orders.feature").write_text(orders)
    (tmp_path / "users.feature").write_text(users)
    exit_code = gate.main(["--dir", str(tmp_path)])
    assert exit_code == 1
    out = capsys.readouterr().out
    assert "\x1b" not in out
    assert "POST /orders" in out


def test_main_strips_control_characters_from_dirs_display_when_dir_is_missing(tmp_path, capsys):
    """--dir is composed by gherkin-derive from a probe of the target repo,
    not always typed by a human — the WARN branch's dirs_display needs the
    same guard as a scanned file's path, since it's the same untrusted-path
    class."""
    hostile_dir = tmp_path / "nope\x1b[31m"
    exit_code = gate.main(["--dir", str(hostile_dir)])
    assert exit_code == 2
    out = capsys.readouterr().out
    assert "\x1b" not in out
    assert "no .feature files found" in out
