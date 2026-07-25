"""Unit tests for scripts/gherkin_feature_merge.py (issue #1420).

Covers the Feature-block parser (Step 1.1), append-only merge with defined
failure modes (Step 1.2), the merge/check-stale CLI (Step 1.3), and the
deterministic stale-scenario match check (Step 2.1).
"""

from __future__ import annotations

import json
import subprocess
import sys

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "scripts"))

import gherkin_feature_merge as gfm

SCRIPT = _REPO_ROOT / "plugins" / "dev-team" / "scripts" / "gherkin_feature_merge.py"

ORDERS_FEATURE = """Feature: Orders API

  @smoke
  Scenario Outline: Create order succeeds with valid payload
    Given a valid payload <payload>
    When the order is created
    Then the response status is 201

    Examples:
      | payload |
      | valid   |
"""

BACKGROUND_FEATURE = """Feature: Orders API

  Background:
    Given the orders service is running

  Scenario: Create order succeeds with valid payload
    Given a valid payload
    When the order is created
    Then the response status is 201
"""


# ---------------------------------------------------------------------------
# parse_feature_block (Step 1.1)
# ---------------------------------------------------------------------------


def test_parses_background_tag_and_outline_examples_in_order():
    result = gfm.parse_feature_block(BACKGROUND_FEATURE, "Orders API")
    assert result.error is None
    assert result.block.background is not None
    assert "orders service is running" in result.block.background
    assert [u.title for u in result.block.units] == ["Create order succeeds with valid payload"]


def test_parses_tagged_scenario_outline_with_examples_as_one_unit():
    result = gfm.parse_feature_block(ORDERS_FEATURE, "Orders API")
    assert result.error is None
    assert len(result.block.units) == 1
    unit = result.block.units[0]
    assert unit.title == "Create order succeeds with valid payload"
    assert "@smoke" in unit.text
    assert "Examples:" in unit.text
    assert "| valid   |" in unit.text


def test_feature_title_not_found_returns_feature_not_found():
    result = gfm.parse_feature_block(ORDERS_FEATURE, "Nonexistent Surface")
    assert result.error == "feature-not-found"
    assert result.block is None


def test_dangling_tag_with_no_scenario_is_malformed():
    text = "Feature: Orders API\n\n  @smoke\n"
    result = gfm.parse_feature_block(text, "Orders API")
    assert result.error == "malformed-feature-block"
    assert result.block is None


def test_scenario_outline_missing_examples_table_is_malformed():
    text = (
        "Feature: Orders API\n\n"
        "  Scenario Outline: Create order succeeds\n"
        "    Given a payload\n"
        "    Examples:\n"
    )
    result = gfm.parse_feature_block(text, "Orders API")
    assert result.error == "malformed-feature-block"


def test_crlf_and_missing_trailing_newline_parse_identically():
    lf_text = ORDERS_FEATURE.rstrip("\n")
    crlf_text = lf_text.replace("\n", "\r\n")
    lf_result = gfm.parse_feature_block(lf_text, "Orders API")
    crlf_result = gfm.parse_feature_block(crlf_text, "Orders API")
    assert lf_result.error is None
    assert crlf_result.error is None
    assert [u.title for u in lf_result.block.units] == [u.title for u in crlf_result.block.units]


def test_title_whitespace_is_trimmed_for_matching():
    result = gfm.parse_feature_block(ORDERS_FEATURE, "  Orders API  ")
    assert result.error is None


# ---------------------------------------------------------------------------
# merge_scenarios (Step 1.2)
# ---------------------------------------------------------------------------


def _unit(title: str, then: str = "Then the response status is 201") -> gfm.ScenarioUnit:
    text = f"  Scenario: {title}\n    Given a precondition\n    When an action\n    {then}\n"
    return gfm.ScenarioUnit(title=title, line=0, text=text)


def test_three_new_candidates_all_appended_in_order():
    candidates = [_unit("New scenario A"), _unit("New scenario B"), _unit("New scenario C")]
    result = gfm.merge_scenarios(ORDERS_FEATURE, "Orders API", candidates)
    assert result.error is None
    assert result.added_titles == ["New scenario A", "New scenario B", "New scenario C"]
    assert result.text.startswith(ORDERS_FEATURE)
    idx_a = result.text.index("New scenario A")
    idx_b = result.text.index("New scenario B")
    idx_c = result.text.index("New scenario C")
    assert idx_a < idx_b < idx_c


def test_all_duplicate_titles_leaves_text_unchanged():
    candidates = [_unit("Create order succeeds with valid payload")]
    result = gfm.merge_scenarios(ORDERS_FEATURE, "Orders API", candidates)
    assert result.text == ORDERS_FEATURE
    assert result.added_titles == []
    assert result.skipped_duplicate_titles == ["Create order succeeds with valid payload"]


def test_duplicate_title_differing_only_by_whitespace_is_still_skipped():
    candidates = [_unit("  Create order succeeds with valid payload  ")]
    result = gfm.merge_scenarios(ORDERS_FEATURE, "Orders API", candidates)
    assert result.added_titles == []
    assert result.skipped_duplicate_titles


def test_no_existing_text_synthesizes_fresh_block():
    candidates = [_unit("First scenario")]
    result = gfm.merge_scenarios("", "Orders API", candidates)
    assert result.error is None
    assert result.text.startswith("Feature: Orders API")
    assert "First scenario" in result.text
    assert result.added_titles == ["First scenario"]


def test_title_not_found_in_nonempty_existing_text_is_feature_not_found():
    result = gfm.merge_scenarios(ORDERS_FEATURE, "Nonexistent Surface", [_unit("X")])
    assert result.error == "feature-not-found"
    assert result.text == ORDERS_FEATURE


def test_malformed_existing_block_with_matching_title_is_malformed_not_not_found():
    text = "Feature: Orders API\n\n  @smoke\n"
    result = gfm.merge_scenarios(text, "Orders API", [_unit("X")])
    assert result.error == "malformed-feature-block"
    assert result.text == text


def test_append_lands_after_examples_table_not_inside_it():
    candidates = [_unit("Second scenario")]
    result = gfm.merge_scenarios(ORDERS_FEATURE, "Orders API", candidates)
    examples_idx = result.text.index("| valid   |")
    second_idx = result.text.index("Second scenario")
    assert examples_idx < second_idx


def test_background_and_tag_preserved_byte_for_byte_across_merge():
    candidates = [_unit("Unrelated new scenario")]
    result = gfm.merge_scenarios(BACKGROUND_FEATURE, "Orders API", candidates)
    assert "Background:" in result.text
    assert "the orders service is running" in result.text
    assert result.text.startswith(BACKGROUND_FEATURE)


# ---------------------------------------------------------------------------
# CLI (Step 1.3)
# ---------------------------------------------------------------------------


def _run_cli(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, check=False
    )


def test_cli_merge_writes_file_and_reports_added_titles(tmp_path):
    existing = tmp_path / "orders.feature"
    existing.write_text(ORDERS_FEATURE, encoding="utf-8")
    candidates = tmp_path / "candidates.txt"
    candidates.write_text(_unit("New one").text + _unit("New two").text, encoding="utf-8")

    proc = _run_cli(
        "merge",
        "--existing",
        str(existing),
        "--candidates",
        str(candidates),
        "--feature-title",
        "Orders API",
        "--json",
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["added_titles"] == ["New one", "New two"]
    assert "New one" in existing.read_text(encoding="utf-8")


def test_cli_merge_many_headerless_candidates_parse_into_units(tmp_path):
    existing = tmp_path / "orders.feature"
    existing.write_text(ORDERS_FEATURE, encoding="utf-8")
    candidates = tmp_path / "candidates.txt"
    candidates.write_text(
        _unit("Three A").text + _unit("Three B").text + _unit("Three C").text, encoding="utf-8"
    )
    proc = _run_cli(
        "merge",
        "--existing",
        str(existing),
        "--candidates",
        str(candidates),
        "--feature-title",
        "Orders API",
        "--json",
    )
    payload = json.loads(proc.stdout)
    assert payload["added_titles"] == ["Three A", "Three B", "Three C"]


def test_cli_merge_title_mismatch_exits_2_and_leaves_file_unchanged(tmp_path):
    existing = tmp_path / "orders.feature"
    existing.write_text(ORDERS_FEATURE, encoding="utf-8")
    before = existing.read_text(encoding="utf-8")
    candidates = tmp_path / "candidates.txt"
    candidates.write_text(_unit("New one").text, encoding="utf-8")

    proc = _run_cli(
        "merge",
        "--existing",
        str(existing),
        "--candidates",
        str(candidates),
        "--feature-title",
        "Nonexistent Surface",
    )
    assert proc.returncode == 2
    assert "Nonexistent Surface" in proc.stderr
    assert existing.read_text(encoding="utf-8") == before


def test_cli_merge_malformed_existing_block_exits_2_and_leaves_file_unchanged(tmp_path):
    existing = tmp_path / "orders.feature"
    existing.write_text("Feature: Orders API\n\n  @smoke\n", encoding="utf-8")
    before = existing.read_text(encoding="utf-8")
    candidates = tmp_path / "candidates.txt"
    candidates.write_text(_unit("New one").text, encoding="utf-8")

    proc = _run_cli(
        "merge",
        "--existing",
        str(existing),
        "--candidates",
        str(candidates),
        "--feature-title",
        "Orders API",
    )
    assert proc.returncode == 2
    assert "parse failure" in proc.stderr.lower() or "malformed" in proc.stderr.lower()
    assert existing.read_text(encoding="utf-8") == before


def test_cli_merge_dry_run_never_touches_filesystem(tmp_path):
    existing = tmp_path / "orders.feature"
    existing.write_text(ORDERS_FEATURE, encoding="utf-8")
    before_mtime = existing.stat().st_mtime
    candidates = tmp_path / "candidates.txt"
    candidates.write_text(_unit("New one").text, encoding="utf-8")

    proc = _run_cli(
        "merge",
        "--existing",
        str(existing),
        "--candidates",
        str(candidates),
        "--feature-title",
        "Orders API",
        "--dry-run",
    )
    assert proc.returncode == 0
    assert existing.stat().st_mtime == before_mtime
    assert existing.read_text(encoding="utf-8") == ORDERS_FEATURE


# ---------------------------------------------------------------------------
# find_then_step_text / is_stale (Step 2.1)
# ---------------------------------------------------------------------------


def test_then_text_containing_observed_value_is_not_stale():
    then_text = "Then the response status is 201\n"
    assert gfm.is_stale(then_text, "201") is False


def test_then_text_not_containing_observed_value_is_stale():
    then_text = "Then the response status is 201\n"
    assert gfm.is_stale(then_text, "202") is True


def test_then_and_continuation_lines_are_joined_and_still_match():
    text = (
        "Feature: Orders API\n\n"
        "  Scenario: Create order succeeds\n"
        "    Given a payload\n"
        "    When created\n"
        "    Then the response status is 201\n"
        "    And the body contains an order id\n"
    )
    then_texts = gfm.find_then_step_text(text, "Orders API")
    assert "order id" in then_texts["Create order succeeds"]
    assert gfm.is_stale(then_texts["Create order succeeds"], "201") is False


def test_scenario_with_no_then_step_returns_empty_and_never_stale():
    text = "Feature: Orders API\n\n  Scenario: Weird\n    Given a payload\n"
    then_texts = gfm.find_then_step_text(text, "Orders API")
    assert then_texts["Weird"] == ""
    assert gfm.is_stale(then_texts["Weird"], "anything") is False


def test_cli_check_stale_reports_mismatch_as_json(tmp_path):
    existing = tmp_path / "orders.feature"
    existing.write_text(ORDERS_FEATURE, encoding="utf-8")
    proc = _run_cli(
        "check-stale",
        "--existing",
        str(existing),
        "--feature-title",
        "Orders API",
        "--observed",
        "Create order succeeds with valid payload=202",
        "--json",
    )
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["findings"][0]["observed"] == "202"
