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


# ---------------------------------------------------------------------------
# iter_slice_body_lines — fence-aware body iterator (#2275)
# ---------------------------------------------------------------------------

_PARITY_FIXTURES = {
    "single gherkin fence": """### Slice 1: First
**Behavior:**

```gherkin
Feature: f
  Scenario: a
    Given x
```
#### Step 1.1: do it
""",
    "non-gherkin fence first, a second gherkin fence ignored": """### Slice 1: First

```bash
### Slice 9: not a heading
echo hi
```

```gherkin
Feature: f
  Scenario: kept
```

```gherkin
Feature: g
  Scenario: dropped
```
""",
    "heading-like and doc-string lines inside the fence": """### Slice 1: First

```gherkin
Feature: f
  Scenario: a
    Given a doc string
      \"\"\"
      ## Not a heading
      #### Step 9.9: not a step
      \"\"\"
```
**Covers**: AC1
""",
}


def _fenced_blocks(text: str) -> list[tuple[str, list[str]]]:
    """Group the iterator's in-fence lines into (opening line, body lines)."""
    blocks: list[tuple[str, list[str]]] = []
    opener: str | None = None
    body: list[str] = []
    for line, in_fence in plan_parse.iter_slice_body_lines(text):
        if not in_fence:
            assert opener is None, "fence left open on a prose line"
            continue
        if opener is None:
            opener, body = line, []
        elif line.startswith("```"):
            blocks.append((opener, body))
            opener = None
        else:
            body.append(line)
    if opener is not None:
        blocks.append((opener, body))
    return blocks


def test_body_iterator_agrees_with_slice_gherkin_blocks_on_the_gherkin_fence():
    for name, text in _PARITY_FIXTURES.items():
        expected = plan_parse.slice_gherkin_blocks(text.splitlines())[0][2]
        gherkin = [
            b for op, b in _fenced_blocks(text) if op[3:].strip().lower() == "gherkin"
        ]
        assert gherkin, name
        assert "\n".join(gherkin[0]) + "\n" == expected, name


def test_body_iterator_flags_every_fence_line_and_no_prose_line():
    text = "prose\n```bash\nin 1\n```\nafter\n"
    assert list(plan_parse.iter_slice_body_lines(text)) == [
        ("prose", False),
        ("```bash", True),
        ("in 1", True),
        ("```", True),
        ("after", False),
    ]


def test_body_iterator_treats_an_unterminated_fence_as_open_to_the_end():
    text = "```gherkin\nScenario: a\n### Slice 2: x\n"
    assert [flag for _, flag in plan_parse.iter_slice_body_lines(text)] == [True] * 3


def test_body_iterator_empty_text_yields_nothing():
    assert list(plan_parse.iter_slice_body_lines("")) == []
