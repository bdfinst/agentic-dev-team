"""Unit tests for scripts/gherkin_feature_merge.py (issue #1420).

Covers the Feature-block parser (Step 1.1), append-only merge with defined
failure modes (Step 1.2), the merge/check-stale CLI (Step 1.3), and the
deterministic stale-scenario match check (Step 2.1).
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

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

# Combines Background + an @smoke-tagged Scenario + a Scenario Outline with
# Examples in one block — Step 1.1's plan TEST note asks for all three
# together (not split across disjoint fixtures), since _find_background's
# returned body_start feeds directly into _parse_units and a boundary bug
# at that seam (e.g. an Outline immediately after a Background) would
# otherwise hide.
BACKGROUND_AND_OUTLINE_FEATURE = """Feature: Orders API

  Background:
    Given the orders service is running

  @smoke
  Scenario: Create order succeeds with valid payload
    Given a valid payload
    When the order is created
    Then the response status is 201

  Scenario Outline: Create order fails for <reason>
    Given a payload missing <reason>
    Then the response status is 400

    Examples:
      | reason  |
      | address |
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


def test_parses_background_tagged_scenario_and_outline_together_in_order():
    """Step 1.1's plan TEST note: one fixture combining a Background, an
    @smoke-tagged Scenario, and a Scenario Outline+Examples all together —
    not split across disjoint fixtures — parses into the Background plus 2
    correctly-bounded, correctly-ordered units."""
    result = gfm.parse_feature_block(BACKGROUND_AND_OUTLINE_FEATURE, "Orders API")
    assert result.error is None
    assert result.block.background is not None
    assert "orders service is running" in result.block.background
    assert [u.title for u in result.block.units] == [
        "Create order succeeds with valid payload",
        "Create order fails for <reason>",
    ]
    assert "@smoke" in result.block.units[0].text
    assert "Examples:" in result.block.units[1].text
    assert "| address |" in result.block.units[1].text


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


def test_background_and_tag_both_preserved_across_a_merge_that_adds_one_scenario():
    """Step 1.2's edge case explicitly wants Background AND an @tag line
    both present in the same merge, not exercised separately."""
    text = (
        "Feature: Orders API\n\n"
        "  Background:\n"
        "    Given the orders service is running\n\n"
        "  @smoke\n"
        "  Scenario: Create order succeeds with valid payload\n"
        "    Given a valid payload\n"
        "    When the order is created\n"
        "    Then the response status is 201\n"
    )
    candidates = [_unit("Unrelated new scenario")]
    result = gfm.merge_scenarios(text, "Orders API", candidates)
    assert result.error is None
    assert result.text.startswith(text)
    assert "@smoke" in result.text
    assert "the orders service is running" in result.text


def test_merge_onto_existing_text_missing_a_trailing_newline_does_not_fuse_lines():
    """Regression test (correctness-review): a splice right at end_index with
    no guard on the preceding line's terminator used to concatenate the new
    scenario directly onto the existing file's last line with no separator,
    corrupting it — e.g. 'Then the response status is 201  Scenario: New...'.
    The existing text has no trailing newline here on purpose."""
    text = (
        "Feature: Orders API\n\n"
        "  Scenario: Create order succeeds with valid payload\n"
        "    Given a valid payload\n"
        "    When the order is created\n"
        "    Then the response status is 201"
    )
    assert not text.endswith("\n")
    candidates = [_unit("New scenario")]
    result = gfm.merge_scenarios(text, "Orders API", candidates)
    assert result.error is None
    assert "201\n  Scenario: New scenario" in result.text
    assert "201  Scenario: New scenario" not in result.text
    assert result.text.startswith(text.rstrip("\n"))


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


def test_parse_candidate_units_malformed_text_reports_error_not_silent_empty():
    """Regression test (correctness-review): a malformed --candidates
    fragment used to collapse to an empty, error-less list — indistinguish-
    able from 'the file had zero scenarios'. It must report the same
    malformed-feature-block error parse_feature_block would, not disappear."""
    units, error = gfm.parse_candidate_units("  @dangling-tag-with-no-scenario\n")
    assert units == []
    assert error == "malformed-feature-block"


def test_parse_candidate_units_well_formed_text_reports_no_error():
    units, error = gfm.parse_candidate_units(_unit("New one").text)
    assert error is None
    assert [u.title for u in units] == ["New one"]


def test_cli_merge_malformed_candidates_exits_2_and_leaves_file_unchanged(tmp_path):
    existing = tmp_path / "orders.feature"
    existing.write_text(ORDERS_FEATURE, encoding="utf-8")
    before = existing.read_text(encoding="utf-8")
    candidates = tmp_path / "candidates.txt"
    candidates.write_text("  @dangling-tag-with-no-scenario\n", encoding="utf-8")

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
    assert existing.read_text(encoding="utf-8") == before
    assert "malformed" in proc.stderr.lower()


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


def test_but_continuation_line_is_captured_alongside_and():
    """Regression test (domain-review): Gherkin permits `But` as a
    Then-continuation, not just `And`. Omitting it would silently drop part
    of the asserted behavior from the stale-scenario comparison."""
    text = (
        "Feature: Orders API\n\n"
        "  Scenario: Create order fails\n"
        "    Given an invalid payload\n"
        "    When the order is rejected\n"
        "    Then the request is rejected\n"
        "    But no partial record is written\n"
    )
    then_texts = gfm.find_then_step_text(text, "Orders API")
    assert "no partial record is written" in then_texts["Create order fails"]


def test_cli_check_stale_reports_unmatched_observed_title_distinctly(tmp_path):
    """Regression test (domain-review): an --observed title that isn't an
    exact key in the retained block used to silently no-op, indistinguish-
    able from 'nothing to compare' — masking exactly the drift this command
    exists to detect (e.g. the caller's title extraction diverged slightly
    from the retained scenario's exact text)."""
    existing = tmp_path / "orders.feature"
    existing.write_text(ORDERS_FEATURE, encoding="utf-8")
    proc = _run_cli(
        "check-stale",
        "--existing",
        str(existing),
        "--feature-title",
        "Orders API",
        "--observed",
        "A title that does not exist=201",
        "--json",
    )
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["findings"] == []
    assert payload["unmatched_titles"] == ["A title that does not exist"]


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


# ---------------------------------------------------------------------------
# _write_atomic — crash-safety (issue #1420 follow-up review, concurrency-review)
# ---------------------------------------------------------------------------


def test_write_atomic_leaves_no_temp_file_on_success(tmp_path):
    target = tmp_path / "orders.feature"
    gfm._write_atomic(target, "written content")
    assert target.read_text(encoding="utf-8") == "written content"
    assert list(tmp_path.iterdir()) == [target]


def test_write_atomic_leaves_original_untouched_on_replace_failure(tmp_path, monkeypatch):
    target = tmp_path / "orders.feature"
    target.write_text("original content", encoding="utf-8")

    def _boom(*_args, **_kwargs):
        raise OSError("simulated crash mid-write")

    monkeypatch.setattr(gfm.os, "replace", _boom)

    with pytest.raises(OSError):
        gfm._write_atomic(target, "new content")

    assert target.read_text(encoding="utf-8") == "original content"
    assert list(tmp_path.iterdir()) == [target]
