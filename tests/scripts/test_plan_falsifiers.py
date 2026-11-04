"""Unit tests for plugins/dev-team/scripts/plan_falsifiers.py.

Behavioral contract (Slice 1 of plans/2271-scenario-falsifier.md): the script
lists every Scenario / Scenario Outline in a plan's first gherkin fence per
slice with its "Still passes if:" falsifier, and reports scenarios whose
falsifier is absent, misplaced, wrong-case, or empty as `missing`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parents[2] / "plugins" / "dev-team" / "scripts"
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from plan_falsifiers import FALSIFIER_PREFIX  # type: ignore[import-not-found]

_SCRIPT = _SCRIPT_DIR / "plan_falsifiers.py"
_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "plan-falsifiers"
_FALSIFIER = f"# {FALSIFIER_PREFIX}"


def _slice(number: int, gherkin: str | None) -> str:
    """One template-shaped slice section; no gherkin fence when `gherkin` is None."""
    section = f"### Slice {number}: Slice {number} title\n\n**Depends-on:** none\n\n**Behavior:**\n\n"
    if gherkin is not None:
        section += f"```gherkin\n{gherkin}```\n\n"
    return section + "**Steps:**\n\n"


def _write_plan(tmp_path: Path, *slices: str) -> Path:
    path = tmp_path / "plan.md"
    path.write_text("# Plan: Sample\n\n## Slices\n\n" + "".join(slices), encoding="utf-8")
    return path


def _run(*args: object) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *map(str, args)],
        capture_output=True,
        text=True,
        check=False,
    )


def _scan(tmp_path: Path, *gherkins: str) -> dict:
    """Run the script on a plan with one slice per gherkin string; return its JSON."""
    plan = _write_plan(tmp_path, *(_slice(n, g) for n, g in enumerate(gherkins, 1)))
    result = _run(plan)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _scenario(title: str, *body: str) -> str:
    return f"  Scenario: {title}\n" + "".join(f"    {line}\n" for line in body)


def test_every_scenario_carries_a_falsifier():
    result = _run(_FIXTURES / "complete.md")
    out = json.loads(result.stdout)
    assert result.returncode == 0
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
    result = _run(_FIXTURES / "missing-one.md")
    out = json.loads(result.stdout)
    assert result.returncode == 0
    assert out["missing"] == [{"slice": "2", "scenario": "Gamma works"}]
    assert len(out["scenarios"]) == 3
    assert out["scenarios"][-1] == {"slice": "2", "scenario": "Gamma works", "falsifier": None}


def test_output_has_the_documented_key_set_and_string_slice_ids():
    out = json.loads(_run(_FIXTURES / "missing-one.md").stdout)
    assert set(out) == {"scenarios", "missing", "scanned_slices", "skipped_slices", "error"}
    assert all(set(row) == {"slice", "scenario", "falsifier"} for row in out["scenarios"])
    assert all(set(row) == {"slice", "scenario"} for row in out["missing"])
    assert all(type(row["slice"]) is str for row in out["scenarios"])
    assert all(type(row["slice"]) is str for row in out["missing"])


def test_empty_falsifier_counts_as_missing(tmp_path):
    out = _scan(tmp_path, _scenario("Blank one", f"{_FALSIFIER}   ", "Given x"))
    assert out["missing"] == [{"slice": "1", "scenario": "Blank one"}]
    assert out["scenarios"][0]["falsifier"] is None


def test_single_character_falsifier_is_accepted(tmp_path):
    out = _scan(tmp_path, _scenario("Tiny", f"{_FALSIFIER} x", "Given x"))
    assert out["scenarios"][0]["falsifier"] == "x"
    assert out["missing"] == []


def test_falsifier_after_a_step_counts_as_missing(tmp_path):
    out = _scan(tmp_path, _scenario("Late", "Given x", f"{_FALSIFIER} too late"))
    assert out["missing"] == [{"slice": "1", "scenario": "Late"}]
    assert out["scenarios"][0]["falsifier"] is None


def test_wrong_case_key_counts_as_missing(tmp_path):
    out = _scan(tmp_path, _scenario("Cased", "# still passes if: x", "Given x"))
    assert out["missing"] == [{"slice": "1", "scenario": "Cased"}]


def test_blank_lines_before_the_falsifier_are_allowed(tmp_path):
    gherkin = f"  Scenario: Spaced\n\n\n    {_FALSIFIER} spacing varies\n    Given x\n"
    out = _scan(tmp_path, gherkin)
    assert out["scenarios"][0]["falsifier"] == "spacing varies"
    assert out["missing"] == []


def test_another_comment_before_the_falsifier_counts_as_missing(tmp_path):
    gherkin = _scenario("Noted", "# an unrelated note", f"{_FALSIFIER} x", "Given x")
    out = _scan(tmp_path, gherkin)
    assert out["missing"] == [{"slice": "1", "scenario": "Noted"}]


def test_scenario_indentation_does_not_matter(tmp_path):
    gherkin = (
        f"Scenario: Flush\n{_FALSIFIER} flush text\nGiven x\n\n"
        f"    Scenario: Indented\n    {_FALSIFIER} indented text\n    Given y\n"
    )
    out = _scan(tmp_path, gherkin)
    assert [(r["scenario"], r["falsifier"]) for r in out["scenarios"]] == [
        ("Flush", "flush text"),
        ("Indented", "indented text"),
    ]


def test_background_block_needs_no_falsifier(tmp_path):
    gherkin = (
        "Feature: F\n\n  Background:\n"
        f"    {_FALSIFIER} background text\n    Given a setup\n\n"
        + _scenario("Only one", f"{_FALSIFIER} the only row", "Given x")
    )
    out = _scan(tmp_path, gherkin)
    assert [r["scenario"] for r in out["scenarios"]] == ["Only one"]
    assert out["missing"] == []


def test_scenario_outline_is_listed(tmp_path):
    gherkin = (
        f"  Scenario Outline: With\n    {_FALSIFIER} rows vary\n    Given <a>\n\n"
        "    Examples:\n      | a |\n      | 1 |\n\n"
        "  Scenario Outline: Without\n    Given <a>\n\n    Examples:\n      | a |\n"
    )
    out = _scan(tmp_path, gherkin)
    assert [r["scenario"] for r in out["scenarios"]] == ["With", "Without"]
    assert out["missing"] == [{"slice": "1", "scenario": "Without"}]


def test_scenarios_are_attributed_to_their_slice(tmp_path):
    two = _scenario("One", f"{_FALSIFIER} a") + _scenario("Two", f"{_FALSIFIER} b")
    plan = _write_plan(tmp_path, _slice(1, two), _slice(3, None))
    out = json.loads(_run(plan).stdout)
    assert [(r["slice"], r["scenario"]) for r in out["scenarios"]] == [("1", "One"), ("1", "Two")]
    assert out["scanned_slices"] == ["1"]
    assert out["skipped_slices"] == ["3"]


def test_only_the_first_gherkin_fence_per_slice_is_scanned(tmp_path):
    first = _scenario("Seen", f"{_FALSIFIER} a")
    second = _scenario("Unseen", "Given no falsifier")
    section = _slice(1, first) + f"```gherkin\n{second}```\n\n"
    plan = _write_plan(tmp_path, section)
    out = json.loads(_run(plan).stdout)
    assert [r["scenario"] for r in out["scenarios"]] == ["Seen"]
    assert out["missing"] == []


def test_duplicate_titles_are_not_merged(tmp_path):
    gherkin = _scenario("Same", f"{_FALSIFIER} a") + _scenario("Same", "Given x")
    out = _scan(tmp_path, gherkin)
    assert [r["scenario"] for r in out["scenarios"]] == ["Same", "Same"]
    assert out["missing"] == [{"slice": "1", "scenario": "Same"}]


def test_gherkin_fence_with_no_scenarios_is_scanned_and_empty(tmp_path):
    out = _scan(tmp_path, "Feature: Nothing yet\n")
    assert out["scenarios"] == []
    assert out["missing"] == []
    assert out["scanned_slices"] == ["1"]
    assert out["skipped_slices"] == []


def test_plan_without_gherkin_skips_every_slice(tmp_path):
    plan = _write_plan(tmp_path, _slice(1, None), _slice(2, None))
    result = _run(plan)
    out = json.loads(result.stdout)
    assert result.returncode == 0
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
