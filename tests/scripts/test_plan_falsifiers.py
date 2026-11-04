"""Unit tests for plugins/dev-team/scripts/plan_falsifiers.py.

Behavioral contract: every Scenario / Scenario Outline in a slice's first
gherkin fence is listed with its "Still passes if:" falsifier; absent,
misplaced, wrong-case, or empty falsifiers are reported as `missing`.
Logic is tested in-process through `build_falsifier_report`; subprocess runs
cover only the CLI contract (exit codes, stdout JSON, stderr).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT_DIR = Path(__file__).resolve().parents[2] / "plugins" / "dev-team" / "scripts"
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from plan_falsifiers import (  # type: ignore[import-not-found]
    FALSIFIER_PREFIX,
    build_falsifier_report,
)

_SCRIPT = _SCRIPT_DIR / "plan_falsifiers.py"
_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "plan-falsifiers"
_FALSIFIER_COMMENT_PREFIX = f"# {FALSIFIER_PREFIX}"


def _slice_section(number: int, gherkin: str | None) -> str:
    """One template-shaped slice section; no gherkin fence when `gherkin` is None."""
    section = f"### Slice {number}: Slice {number} title\n\n**Depends-on:** none\n\n**Behavior:**\n\n"
    if gherkin is not None:
        section += f"```gherkin\n{gherkin}```\n\n"
    return section + "**Steps:**\n\n"


def _plan_text(*slices: str) -> str:
    return "# Plan: Sample\n\n## Slices\n\n" + "".join(slices)


def _report_for_plan(*slices: str) -> dict:
    """In-process report for a plan made of the given slice sections."""
    return build_falsifier_report(_plan_text(*slices).split("\n"))


def _scan(*gherkins: str) -> dict:
    """In-process report for a plan with one slice per gherkin string."""
    return _report_for_plan(*(_slice_section(n, g) for n, g in enumerate(gherkins, 1)))


def _run(*args: object) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *map(str, args)],
        capture_output=True,
        text=True,
        check=False,
    )


def _run_ok(*args: object) -> dict:
    """Run the script, require exit 0, and return its parsed stdout."""
    result = _run(*args)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _scenario_block(title: str, *body: str) -> str:
    return f"  Scenario: {title}\n" + "".join(f"    {line}\n" for line in body)


_KEY_SET = {"scenarios", "missing", "scanned_slices", "skipped_slices", "error"}


def test_every_scenario_carries_a_falsifier():
    out = _run_ok(_FIXTURES / "complete.md")
    assert out["scenarios"] == [
        {"slice": "1", "scenario": "Alpha works", "falsifier": "the key order changes"},
        {
            "slice": "2",
            "scenario": "Beta handles <kind>",
            "falsifier": "the Examples table gains a row",
        },
    ]
    assert out["missing"] == []
    assert out["skipped_slices"] == []
    assert out["error"] is None


def test_one_scenario_without_a_falsifier_is_missing():
    text = (_FIXTURES / "missing-one.md").read_text(encoding="utf-8")
    out = build_falsifier_report(text.split("\n"))
    assert out["missing"] == [{"slice": "2", "scenario": "Gamma works"}]
    assert len(out["scenarios"]) == 3
    assert out["scenarios"][-1] == {"slice": "2", "scenario": "Gamma works", "falsifier": None}


def test_output_has_the_documented_key_set_and_string_slice_ids():
    out = _run_ok(_FIXTURES / "missing-one.md")
    assert set(out) == _KEY_SET
    assert all(set(row) == {"slice", "scenario", "falsifier"} for row in out["scenarios"])
    assert all(set(row) == {"slice", "scenario"} for row in out["missing"])
    assert all(type(row["slice"]) is str for row in out["scenarios"])
    assert all(type(row["slice"]) is str for row in out["missing"])


def test_unreadable_output_has_the_same_key_set_as_a_readable_one(tmp_path):
    result = _run(tmp_path / "nope.md")
    assert result.returncode == 2
    assert set(json.loads(result.stdout)) == _KEY_SET


def test_empty_falsifier_counts_as_missing():
    out = _scan(_scenario_block("Blank one", f"{_FALSIFIER_COMMENT_PREFIX}   ", "Given x"))
    assert out["missing"] == [{"slice": "1", "scenario": "Blank one"}]
    assert out["scenarios"][0]["falsifier"] is None


def test_single_character_falsifier_is_accepted():
    out = _scan(_scenario_block("Tiny", f"{_FALSIFIER_COMMENT_PREFIX} x", "Given x"))
    assert out["scenarios"][0]["falsifier"] == "x"
    assert out["missing"] == []


@pytest.mark.parametrize(
    "comment_line",
    ["#Still passes if:x", "#   Still passes if:   x", "\t# Still passes if: x"],
    ids=["no-spaces", "extra-spaces", "tab-indented"],
)
def test_whitespace_around_the_falsifier_marker_is_tolerated(comment_line):
    out = _scan(f"  Scenario: Spacey\n{comment_line}\n    Given x\n")
    assert out["scenarios"][0]["falsifier"] == "x"
    assert out["missing"] == []


def test_falsifier_after_a_step_counts_as_missing():
    out = _scan(_scenario_block("Late", "Given x", f"{_FALSIFIER_COMMENT_PREFIX} too late"))
    assert out["missing"] == [{"slice": "1", "scenario": "Late"}]
    assert out["scenarios"][0]["falsifier"] is None


def test_wrong_case_key_counts_as_missing():
    out = _scan(_scenario_block("Cased", "# still passes if: x", "Given x"))
    assert out["missing"] == [{"slice": "1", "scenario": "Cased"}]


def test_blank_lines_before_the_falsifier_are_allowed():
    gherkin = f"  Scenario: Spaced\n\n\n    {_FALSIFIER_COMMENT_PREFIX} spacing varies\n    Given x\n"
    out = _scan(gherkin)
    assert out["scenarios"][0]["falsifier"] == "spacing varies"
    assert out["missing"] == []


def test_another_comment_before_the_falsifier_counts_as_missing():
    gherkin = _scenario_block("Noted", "# an unrelated note", f"{_FALSIFIER_COMMENT_PREFIX} x", "Given x")
    out = _scan(gherkin)
    assert out["missing"] == [{"slice": "1", "scenario": "Noted"}]


def test_scenario_indentation_does_not_matter():
    gherkin = (
        f"Scenario: Flush\n{_FALSIFIER_COMMENT_PREFIX} flush text\nGiven x\n\n"
        f"    Scenario: Indented\n    {_FALSIFIER_COMMENT_PREFIX} indented text\n    Given y\n"
    )
    out = _scan(gherkin)
    assert [(r["scenario"], r["falsifier"]) for r in out["scenarios"]] == [
        ("Flush", "flush text"),
        ("Indented", "indented text"),
    ]


def test_background_block_needs_no_falsifier():
    gherkin = (
        "Feature: F\n\n  Background:\n"
        f"    {_FALSIFIER_COMMENT_PREFIX} background text\n    Given a setup\n\n"
        + _scenario_block("Only one", f"{_FALSIFIER_COMMENT_PREFIX} the only row", "Given x")
    )
    out = _scan(gherkin)
    assert [r["scenario"] for r in out["scenarios"]] == ["Only one"]
    assert out["missing"] == []


def test_scenario_outline_is_listed():
    gherkin = (
        f"  Scenario Outline: With\n    {_FALSIFIER_COMMENT_PREFIX} rows vary\n    Given <a>\n\n"
        "    Examples:\n      | a |\n      | 1 |\n\n"
        "  Scenario Outline: Without\n    Given <a>\n\n    Examples:\n      | a |\n"
    )
    out = _scan(gherkin)
    assert [r["scenario"] for r in out["scenarios"]] == ["With", "Without"]
    assert out["missing"] == [{"slice": "1", "scenario": "Without"}]


def test_scenario_without_falsifier_directly_before_one_with_falsifier():
    gherkin = _scenario_block("A") + _scenario_block("B", f"{_FALSIFIER_COMMENT_PREFIX} b text", "Given x")
    out = _scan(gherkin)
    assert [(r["scenario"], r["falsifier"]) for r in out["scenarios"]] == [
        ("A", None),
        ("B", "b text"),
    ]
    assert out["missing"] == [{"slice": "1", "scenario": "A"}]


def test_first_of_two_scenarios_missing_gives_exactly_one_missing_entry():
    gherkin = _scenario_block("First", "Given x") + _scenario_block(
        "Second", f"{_FALSIFIER_COMMENT_PREFIX} second text", "Given y"
    )
    out = _scan(gherkin)
    assert out["missing"] == [{"slice": "1", "scenario": "First"}]


def test_scenarios_are_attributed_to_their_slice():
    two = _scenario_block("One", f"{_FALSIFIER_COMMENT_PREFIX} a") + _scenario_block("Two", f"{_FALSIFIER_COMMENT_PREFIX} b")
    out = _report_for_plan(_slice_section(1, two), _slice_section(3, None))
    assert [(r["slice"], r["scenario"]) for r in out["scenarios"]] == [("1", "One"), ("1", "Two")]
    assert out["scanned_slices"] == ["1"]
    assert out["skipped_slices"] == ["3"]


def test_only_the_first_gherkin_fence_per_slice_is_scanned():
    first = _scenario_block("Seen", f"{_FALSIFIER_COMMENT_PREFIX} a")
    second = _scenario_block("Unseen", "Given no falsifier")
    section = _slice_section(1, first) + f"```gherkin\n{second}```\n\n"
    out = _report_for_plan(section)
    assert [r["scenario"] for r in out["scenarios"]] == ["Seen"]
    assert out["missing"] == []


def test_duplicate_titles_are_not_merged():
    gherkin = _scenario_block("Same", f"{_FALSIFIER_COMMENT_PREFIX} a") + _scenario_block("Same", "Given x")
    out = _scan(gherkin)
    assert [r["scenario"] for r in out["scenarios"]] == ["Same", "Same"]
    assert out["missing"] == [{"slice": "1", "scenario": "Same"}]


def test_gherkin_fence_with_no_scenarios_is_scanned_and_empty():
    out = _scan("Feature: Nothing yet\n")
    assert out["scenarios"] == []
    assert out["missing"] == []
    assert out["scanned_slices"] == ["1"]
    assert out["skipped_slices"] == []


def test_plan_without_gherkin_skips_every_slice():
    out = _report_for_plan(_slice_section(1, None), _slice_section(2, None))
    assert out["scenarios"] == []
    assert out["missing"] == []
    assert out["skipped_slices"] == ["1", "2"]


def _assert_unreadable(result: subprocess.CompletedProcess, path: Path) -> None:
    out = json.loads(result.stdout)
    assert result.returncode == 2
    assert out["scenarios"] == []
    assert out["missing"] == []
    assert str(path) in out["error"]


def test_missing_plan_file_exits_2_and_names_the_path(tmp_path):
    path = tmp_path / "nope.md"
    result = _run(path)
    _assert_unreadable(result, path)
    assert str(path) in result.stderr


def test_directory_path_exits_2_and_names_the_path(tmp_path):
    result = _run(tmp_path)
    _assert_unreadable(result, tmp_path)


def test_undecodable_plan_file_exits_2_and_names_the_path(tmp_path):
    path = tmp_path / "bad.md"
    path.write_bytes(b"# Plan\n\xff\xfe\x80 not utf-8\n")
    result = _run(path)
    _assert_unreadable(result, path)


def test_no_argument_exits_2():
    assert _run().returncode == 2
