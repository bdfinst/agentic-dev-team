"""Unit tests for scripts/plan_waves.py (#589).

A small number of API-level behavioural cases exercising `compute_waves`.
"""

from __future__ import annotations

import sys

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "scripts"))

import plan_waves

# ---------------------------------------------------------------------------
# API-level behavioural tests
# ---------------------------------------------------------------------------


def test_compute_waves_returns_schema(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text(
        "### Slice A: alpha\n"
        "**Depends-on:** none\n"
        "**Files:** `a.ts`\n"
        "### Slice B: beta\n"
        "**Depends-on:** A\n"
        "**Files:** `b.ts`\n"
    )
    payload = plan_waves.compute_waves(plan)
    assert payload["schema"] == "plan-waves/v1"
    assert payload["waves"] == [["A"], ["B"]]
    assert payload["slices"]["A"]["wave"] == 1
    assert payload["slices"]["B"]["depends_on"] == ["A"]


def test_compute_waves_flags_collisions(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text(
        "### Slice A: alpha\n"
        "**Depends-on:** none\n"
        "**Files:** `shared.ts`\n"
        "### Slice B: beta\n"
        "**Depends-on:** none\n"
        "**Files:** `shared.ts`\n"
    )
    payload = plan_waves.compute_waves(plan)
    assert payload["collisions"] == [
        {"wave": 1, "slices": ["A", "B"], "file": "shared.ts"}
    ]


def test_compute_waves_rejects_missing_depends(tmp_path, capsys):
    plan = tmp_path / "plan.md"
    plan.write_text("### Slice A: alpha\n**Files:** `a.ts`\n")
    with pytest.raises(SystemExit) as excinfo:
        plan_waves.compute_waves(plan)
    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "missing its Depends-on declaration" in err


def test_compute_waves_rejects_unknown_reference(tmp_path, capsys):
    plan = tmp_path / "plan.md"
    plan.write_text(
        "### Slice A: alpha\n**Depends-on:** none\n"
        "### Slice B: beta\n**Depends-on:** Z\n"
    )
    with pytest.raises(SystemExit):
        plan_waves.compute_waves(plan)
    err = capsys.readouterr().err
    assert "depends on unknown slice" in err


def test_compute_waves_rejects_cycle(tmp_path, capsys):
    plan = tmp_path / "plan.md"
    plan.write_text(
        "### Slice A: alpha\n**Depends-on:** B\n### Slice B: beta\n**Depends-on:** A\n"
    )
    with pytest.raises(SystemExit):
        plan_waves.compute_waves(plan)
    err = capsys.readouterr().err
    assert "dependency cycle" in err


def test_compute_waves_rejects_empty_plan(tmp_path, capsys):
    plan = tmp_path / "plan.md"
    plan.write_text("no slice headers here\n")
    with pytest.raises(SystemExit):
        plan_waves.compute_waves(plan)
    err = capsys.readouterr().err
    assert "no slices found" in err


# ---------------------------------------------------------------------------
# scope_mismatches (issue #865)
# ---------------------------------------------------------------------------


def test_scope_mismatches_empty_when_no_slice_declares_files(tmp_path):
    """Fieldless plan (AC1): scope_mismatches is always present, [] here."""
    plan = tmp_path / "plan.md"
    plan.write_text("### Slice A: alpha\n**Depends-on:** none\n")
    payload = plan_waves.compute_waves(plan)
    assert payload["scope_mismatches"] == []


def test_scope_mismatches_empty_when_declared_matches_inferred(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text(
        "### Slice A: alpha\n"
        "**Depends-on:** none\n"
        "**Files:** `a.ts`, `b.ts`\n"
        "#### Step A.1: do it\n"
        "**Files**: `a.ts`\n"
        "#### Step A.2: do more\n"
        "**Files**: `b.ts`\n"
    )
    payload = plan_waves.compute_waves(plan)
    assert payload["scope_mismatches"] == []


def test_scope_mismatch_flags_under_declared_the_dangerous_direction(tmp_path):
    """A step touches a file the slice never declared."""
    plan = tmp_path / "plan.md"
    plan.write_text(
        "### Slice A: alpha\n"
        "**Depends-on:** none\n"
        "**Files:** `a.ts`\n"
        "#### Step A.1: do it\n"
        "**Files**: `a.ts`, `undeclared.ts`\n"
    )
    payload = plan_waves.compute_waves(plan)
    assert payload["scope_mismatches"] == [
        {
            "slice": "A",
            "declared": ["a.ts"],
            "inferred": ["a.ts", "undeclared.ts"],
            "under_declared": ["undeclared.ts"],
            "over_declared": [],
        }
    ]


def test_scope_mismatch_flags_over_declared_nothing_touches_it(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text(
        "### Slice A: alpha\n"
        "**Depends-on:** none\n"
        "**Files:** `a.ts`, `never-touched.ts`\n"
        "#### Step A.1: do it\n"
        "**Files**: `a.ts`\n"
    )
    payload = plan_waves.compute_waves(plan)
    assert payload["scope_mismatches"] == [
        {
            "slice": "A",
            "declared": ["a.ts", "never-touched.ts"],
            "inferred": ["a.ts"],
            "under_declared": [],
            "over_declared": ["never-touched.ts"],
        }
    ]


def test_scope_mismatch_glob_pattern_covers_inferred_literal(tmp_path):
    """AC9: a declared glob covers an inferred literal via fnmatch."""
    plan = tmp_path / "plan.md"
    plan.write_text(
        "### Slice A: alpha\n"
        "**Depends-on:** none\n"
        "**Files:** `src/auth/*`\n"
        "#### Step A.1: do it\n"
        "**Files**: `src/auth/session.ts`\n"
    )
    payload = plan_waves.compute_waves(plan)
    assert payload["scope_mismatches"] == []


def test_scope_mismatch_absent_for_slice_with_no_declared_files(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text(
        "### Slice A: alpha\n"
        "**Depends-on:** none\n"
        "#### Step A.1: do it\n"
        "**Files**: `anything.ts`\n"
    )
    payload = plan_waves.compute_waves(plan)
    assert payload["scope_mismatches"] == []


def test_conservative_collision_uses_declared_plus_inferred_union(tmp_path):
    """Same-wave collision detection is conservative (#865): a file only
    referenced at step level (never declared) still trips a collision
    against another slice's overlapping write."""
    plan = tmp_path / "plan.md"
    plan.write_text(
        "### Slice A: alpha\n"
        "**Depends-on:** none\n"
        "**Files:** `a.ts`\n"
        "#### Step A.1: do it\n"
        "**Files**: `shared.ts`\n"
        "### Slice B: beta\n"
        "**Depends-on:** none\n"
        "**Files:** `shared.ts`\n"
    )
    payload = plan_waves.compute_waves(plan)
    assert payload["collisions"] == [
        {"wave": 1, "slices": ["A", "B"], "file": "shared.ts"}
    ]
