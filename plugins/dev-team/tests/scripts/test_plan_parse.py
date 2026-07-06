"""Unit tests for scripts/lib/plan_parse.py (#579).

Two layers of coverage:

1. Behavioural — exercises `parse_slices` on a small hand-authored fixture set
   to lock down the API-level contract (missing depends line yields
   `__MISSING__`, step-level Files lines are ignored, etc.).
2. Byte-parity — dispatches every fixture in `tests/fixtures/plans/` at both
   the `.sh` and `.py` implementations and asserts identical stdout. This is
   the check that guards the eventual rewire in #589 (plan-waves).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import List

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "scripts" / "lib"))

import plan_parse  # noqa: E402


_PLAN_PARSE_SH = (
    _REPO_ROOT / "plugins" / "dev-team" / "scripts" / "lib" / "plan-parse.sh"
)
_PLAN_PARSE_PY = (
    _REPO_ROOT / "plugins" / "dev-team" / "scripts" / "lib" / "plan_parse.py"
)
_FIXTURES_DIR = _REPO_ROOT / "tests" / "fixtures" / "plans"


# ---------------------------------------------------------------------------
# Behavioural tests — API surface
# ---------------------------------------------------------------------------


def _rows(source: str) -> List[tuple]:
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


# ---------------------------------------------------------------------------
# Byte-parity against the bash implementation
# ---------------------------------------------------------------------------


def _fixture_paths() -> List[Path]:
    if not _FIXTURES_DIR.is_dir():
        return []
    return sorted(_FIXTURES_DIR.glob("*.md"))


_FIXTURE_PARAMS = _fixture_paths()


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash required for parity")
@pytest.mark.skipif(not _PLAN_PARSE_SH.is_file(), reason="plan-parse.sh not present")
@pytest.mark.skipif(not _FIXTURE_PARAMS, reason="no plan fixtures present")
@pytest.mark.parametrize("fixture", _FIXTURE_PARAMS, ids=lambda p: p.name)
def test_byte_parity_with_bash(fixture: Path) -> None:
    """Stdout of `plan-parse.sh <fixture>` must equal `plan_parse.py <fixture>`."""
    sh = subprocess.run(
        ["bash", str(_PLAN_PARSE_SH), str(fixture)],
        capture_output=True,
        check=True,
    )
    py = subprocess.run(
        [sys.executable, str(_PLAN_PARSE_PY), str(fixture)],
        capture_output=True,
        check=True,
    )
    assert py.stdout == sh.stdout, (
        f"Byte divergence on {fixture.name}:\nsh: {sh.stdout!r}\npy: {py.stdout!r}"
    )
