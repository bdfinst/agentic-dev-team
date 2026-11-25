"""Unit tests for scripts/plan_lint.py — structural faults in a plan."""

from __future__ import annotations

import sys

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "scripts"))

import plan_lint

CLEAN = """# Plan: demo

**Steps**: 2

## Slices

### Slice 1: alpha
**Depends-on:** none
**Files:** `src/a.py`

#### Step 1.1: write a

**Files**: `src/a.py`, `tests/test_a.py`

#### Step 1.2: use a

Read the `src/a.py` helper and extend it.

**Files**: `src/b.py`
"""


def _write(tmp_path, text):
    plan = tmp_path / "plan.md"
    plan.write_text(text)
    return plan


def _faults(tmp_path, text):
    return plan_lint.lint_plan(_write(tmp_path, text))


def test_clean_plan_has_no_faults(tmp_path):
    assert _faults(tmp_path, CLEAN) == []


def test_step_citing_a_line_of_an_earlier_steps_file_is_a_fault(tmp_path):
    text = CLEAN.replace("Read the `src/a.py` helper", "Read `src/a.py:42`")
    faults = _faults(tmp_path, text)
    assert [f["step"] for f in faults] == ["1.2"]
    assert faults[0]["check"] == "line-citation"
    assert "src/a.py:42" in faults[0]["message"]


def test_line_citation_also_matches_github_anchor_and_range(tmp_path):
    for cite in ("src/a.py#L7", "src/a.py:10-20"):
        text = CLEAN.replace("Read the `src/a.py` helper", f"See {cite}")
        assert [f["check"] for f in _faults(tmp_path, text)] == ["line-citation"]


def test_line_citation_of_a_file_no_earlier_step_writes_is_allowed(tmp_path):
    text = CLEAN.replace("Read the `src/a.py` helper", "Read `docs/x.md:5`")
    assert _faults(tmp_path, text) == []


def test_line_citation_in_the_step_that_writes_the_file_is_allowed(tmp_path):
    text = CLEAN.replace("#### Step 1.1: write a\n", "#### Step 1.1: write a\n\nSee `src/a.py:3`.\n")
    assert _faults(tmp_path, text) == []


def test_step_naming_no_files_is_a_fault(tmp_path):
    text = CLEAN.replace("**Files**: `src/b.py`\n", "")
    faults = _faults(tmp_path, text)
    assert [(f["step"], f["check"]) for f in faults] == [("1.2", "no-files")]


def test_stated_step_count_disagreeing_with_headings_is_a_fault(tmp_path):
    faults = _faults(tmp_path, CLEAN.replace("**Steps**: 2", "**Steps**: 3"))
    assert [f["check"] for f in faults] == ["step-count"]
    assert "3" in faults[0]["message"] and "2" in faults[0]["message"]


def test_plan_without_a_stated_step_count_skips_that_check(tmp_path):
    assert _faults(tmp_path, CLEAN.replace("**Steps**: 2\n", "")) == []


def test_step_identifier_that_is_not_dotted_numbers_is_a_fault(tmp_path):
    faults = _faults(tmp_path, CLEAN.replace("Step 1.2:", "Step 1.2a:"))
    assert [(f["step"], f["check"]) for f in faults] == [("1.2a", "step-id")]


def test_every_fault_is_reported_not_just_the_first(tmp_path):
    text = CLEAN.replace("**Steps**: 2", "**Steps**: 9").replace(
        "**Files**: `src/b.py`\n", ""
    )
    assert {f["check"] for f in _faults(tmp_path, text)} == {"step-count", "no-files"}


def test_main_exits_2_and_names_the_step_on_stderr(tmp_path, capsys):
    plan = _write(tmp_path, CLEAN.replace("**Files**: `src/b.py`\n", ""))
    assert plan_lint.main([str(plan)]) == 2
    assert "step 1.2" in capsys.readouterr().err


def test_main_exits_0_and_prints_json_for_a_clean_plan(tmp_path, capsys):
    plan = _write(tmp_path, CLEAN)
    assert plan_lint.main([str(plan)]) == 0
    assert '"faults": []' in capsys.readouterr().out


def test_main_exits_2_on_a_missing_file(tmp_path):
    assert plan_lint.main([str(tmp_path / "nope.md")]) == 2
