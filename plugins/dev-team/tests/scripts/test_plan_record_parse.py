"""Unit tests for scripts/lib/plan_record_parse.py (#2275).

Behavioural: each parser takes plan text and returns plain data.
"""

from __future__ import annotations

import sys

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "scripts" / "lib"))

import plan_record_parse

# ---------------------------------------------------------------------------
# parse_criteria
# ---------------------------------------------------------------------------


def _ids(text: str) -> list[str]:
    return [c["id"] for c in plan_record_parse.parse_criteria(text)]


def test_criteria_take_an_explicit_prefix_or_their_position():
    md = """## Acceptance Criteria

- [ ] AC1 first
- [x] second
- [ ] AC7 third
"""
    assert plan_record_parse.parse_criteria(md) == [
        {"id": "AC1", "text": "first"},
        {"id": "AC2", "text": "second"},
        {"id": "AC7", "text": "third"},
    ]


def test_criteria_accept_plain_bullets_and_numbered_items():
    md = "## Acceptance Criteria\n- alpha\n1. beta\n2) AC9: gamma\n"
    assert plan_record_parse.parse_criteria(md) == [
        {"id": "AC1", "text": "alpha"},
        {"id": "AC2", "text": "beta"},
        {"id": "AC9", "text": "gamma"},
    ]


def test_a_repeated_explicit_id_keeps_its_text_and_the_later_one_takes_its_position():
    md = "## Acceptance Criteria\n- AC1 one\n- AC1 again\n- AC3 three\n"
    assert plan_record_parse.parse_criteria(md) == [
        {"id": "AC1", "text": "one"},
        {"id": "AC2", "text": "again"},
        {"id": "AC3", "text": "three"},
    ]


def test_an_id_prefix_must_be_a_whole_token():
    assert plan_record_parse.parse_criteria(
        "## Acceptance Criteria\n- AC1x text\n"
    ) == [{"id": "AC1", "text": "AC1x text"}]


def test_criteria_stop_at_the_next_h2_and_ignore_h3_mirror_and_nested_bullets():
    md = """## Acceptance Criteria

- [ ] AC1 top
  - [ ] nested detail
### Notes
- [ ] still the criteria section
## Slices
- [ ] not a criterion
"""
    assert _ids(md) == ["AC1", "AC2"]


def test_criteria_ignore_list_lines_and_headings_inside_a_fence():
    md = """## Acceptance Criteria

```text
- [ ] fenced, not a criterion
## Slices
```
- [ ] real
"""
    assert plan_record_parse.parse_criteria(md) == [{"id": "AC1", "text": "real"}]


def test_a_heading_that_only_starts_with_acceptance_criteria_is_not_the_section():
    md = "## Acceptance Criteria (v2)\n- [ ] AC1 x\n### Acceptance Criteria\n- [ ] y\n"
    assert plan_record_parse.parse_criteria(md) == []


def test_a_missing_criteria_section_reads_as_empty():
    assert plan_record_parse.parse_criteria("# Plan: only a title\n") == []


# ---------------------------------------------------------------------------
# parse_covers
# ---------------------------------------------------------------------------


def test_covers_line_maps_a_step_to_its_criteria():
    md = """#### Step 1.1: do it

**Covers**: AC2, AC7
"""
    assert plan_record_parse.parse_covers(md) == {"1.1": ["AC2", "AC7"]}


def test_covers_line_tolerates_spaces_bold_variants_and_trailing_text():
    md = """#### Step 1.1: a
**Covers:**  AC3 ,AC5 (both) , prose, AC3
#### Step 1.2: b
Covers : AC9 and more
"""
    assert plan_record_parse.parse_covers(md) == {
        "1.1": ["AC3", "AC5"],
        "1.2": ["AC9"],
    }


def test_covers_line_inside_a_fence_is_ignored():
    md = """#### Step 1.1: a

```markdown
**Covers**: AC1
```
"""
    assert plan_record_parse.parse_covers(md) == {}


def test_a_step_heading_inside_a_fence_does_not_take_the_covers_line():
    md = """#### Step 1.1: a

```text
#### Step 9.9: fake
```
**Covers**: AC4
"""
    assert plan_record_parse.parse_covers(md) == {"1.1": ["AC4"]}


def test_several_covers_lines_in_one_step_merge_in_order():
    md = "#### Step 2.3: x\n**Covers**: AC2\n**Covers**: AC1, AC2\n"
    assert plan_record_parse.parse_covers(md) == {"2.3": ["AC2", "AC1"]}


@pytest.mark.parametrize(
    "md",
    [
        "**Covers**: AC1\n#### Step 1.1: after the line\n",
        "#### Step 1.1: x\n**Covers**: <AC ids>\n",
        "#### Step 1.1: x\n**Covers**:\n",
        "",
        "# Plan: only a title\n",
    ],
)
def test_covers_without_a_step_or_without_ids_reads_as_empty(md):
    assert plan_record_parse.parse_covers(md) == {}
