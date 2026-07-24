"""Unit tests for scripts/lib/plan_parse.py (#579).

Behavioural — exercises `parse_slices` on a small hand-authored fixture set
to lock down the API-level contract (missing depends line yields
`__MISSING__`, step-level Files lines are ignored, etc.).
"""

from __future__ import annotations

import sys

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "scripts" / "lib"))

import plan_parse

# ---------------------------------------------------------------------------
# Behavioural tests — API surface
# ---------------------------------------------------------------------------


def _rows(source: str) -> list[tuple]:
    return plan_parse.parse_slices(source.splitlines())


def test_single_slice_with_deps_and_files():
    md = """### Slice 1: First
**Depends-on:** none
**Files:** `one.ts`
"""
    assert _rows(md) == [("1", "none", "one.ts")]


def test_step_level_files_ignored():
    md = """### Slice 1: First
**Depends-on:** none
**Files:** `one.ts`
#### Step 1.1: do it
**Files**: `step-level-should-be-ignored.ts`
"""
    assert _rows(md) == [("1", "none", "one.ts")]


def test_missing_depends_yields_sentinel():
    md = """### Slice A: alpha
**Files:** `a.ts`
### Slice B: beta
**Depends-on:** A
"""
    assert _rows(md) == [
        ("A", "__MISSING__", "a.ts"),
        ("B", "A", ""),
    ]


def test_backticks_and_bold_stripped_from_values():
    md = """### Slice 1: First
**Depends-on:** `2, 3`
**Files:** **`a.ts`, `b.ts`**
"""
    assert _rows(md) == [("1", "2, 3", "a.ts, b.ts")]


def test_slice_id_is_before_first_colon():
    md = """### Slice foo: descriptive title with: colons
**Depends-on:** none
"""
    assert _rows(md) == [("foo", "none", "")]


def test_case_insensitive_depends_and_files_labels():
    md = """### Slice 1: First
depends-on: none
files: `x.ts`
"""
    assert _rows(md) == [("1", "none", "x.ts")]


def test_multiple_slices_ordered_by_source():
    md = """### Slice B: second in file
**Depends-on:** A
### Slice A: first in file after B
**Depends-on:** none
"""
    # Slices come out in source order, not sorted.
    assert _rows(md) == [("B", "A", ""), ("A", "none", "")]


def test_no_slices_yields_empty():
    assert _rows("just a plain markdown file\nwith no slice headers\n") == []


# ---------------------------------------------------------------------------
# Behavioural tests — issue #865: plan-as-contract optional fields
# ---------------------------------------------------------------------------


def test_slice_with_no_optional_fields_parses_unchanged():
    """A slice using none of the three new fields still parses via
    parse_slices exactly as before, and parse_slice_optional_fields reports
    empty invariants/rollback for it."""
    md = """### Slice 1: First
**Depends-on:** none
**Files:** `one.ts`
"""
    assert _rows(md) == [("1", "none", "one.ts")]
    fields = plan_parse.parse_slice_optional_fields(md.splitlines())
    assert fields["1"] == {"invariants": [], "rollback_point": ""}


def test_invariants_and_rollback_point_are_collected_per_slice():
    md = """### Slice 1: First
**Depends-on:** none
**Files:** `a.ts`
**Invariants:** `npm test -- --grep "session"`, `python3 scripts/check_md_references.py`
**Rollback point:** slice-start
"""
    fields = plan_parse.parse_slice_optional_fields(md.splitlines())
    assert fields["1"]["invariants"] == [
        'npm test -- --grep "session"',
        "python3 scripts/check_md_references.py",
    ]
    assert fields["1"]["rollback_point"] == "slice-start"


def test_rollback_point_accepts_explicit_ref():
    md = """### Slice 1: First
**Depends-on:** none
**Rollback point:** abc1234
"""
    fields = plan_parse.parse_slice_optional_fields(md.splitlines())
    assert fields["1"]["rollback_point"] == "abc1234"


def test_invariants_comma_split_fallback_when_no_backticks():
    md = """### Slice 1: First
**Depends-on:** none
**Invariants:** npm test, python3 scripts/check.py
"""
    fields = plan_parse.parse_slice_optional_fields(md.splitlines())
    assert fields["1"]["invariants"] == ["npm test", "python3 scripts/check.py"]


def test_optional_fields_are_slice_level_only_step_level_ignored():
    md = """### Slice 1: First
**Depends-on:** none
#### Step 1.1: do it
**Invariants:** `should-be-ignored`
**Rollback point:** should-be-ignored
"""
    fields = plan_parse.parse_slice_optional_fields(md.splitlines())
    assert fields["1"] == {"invariants": [], "rollback_point": ""}


def test_step_files_union_collects_per_step_files_only():
    md = """### Slice 1: First
**Depends-on:** none
**Files:** `slice-level.ts`
#### Step 1.1: do it
**Files**: `a.ts`
#### Step 1.2: do more
**Files**: `b.ts`, `a.ts`
"""
    result = plan_parse.parse_step_files(md.splitlines())
    assert result == {"1": ["`a.ts`", "`b.ts`, `a.ts`"]}
    union = plan_parse.step_files_union(md.splitlines())
    assert union == {"1": ["a.ts", "b.ts"]}


def test_step_files_union_empty_when_no_step_files():
    md = """### Slice 1: First
**Depends-on:** none
**Files:** `slice-level.ts`
"""
    assert plan_parse.step_files_union(md.splitlines()) == {}
