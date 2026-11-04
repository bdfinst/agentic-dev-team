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


# ---------------------------------------------------------------------------
# parse_scenarios / parse_step_ids
# ---------------------------------------------------------------------------

_SLICE = '''### Slice 1: Parse

**Behavior:**

```gherkin
Feature: f

  Scenario: plain one
    Given a doc string
      """
      Scenario: inside a doc string
      """

  Scenario Outline: an outline
    Given <x>
    Examples:
      | x |
      | 1 |
```

```gherkin
Feature: later fence

  Scenario: y
```

**Steps:**

#### Step 1.1: first
#### Step 1.2: second

```text
#### Step 9.9: fenced, not a step
```

#### Step 1.3: third
'''


def test_scenarios_list_scenario_and_outline_titles_in_order():
    assert plan_record_parse.parse_scenarios(_SLICE) == ["plain one", "an outline"]


def test_a_scenario_word_in_a_doc_string_or_a_later_fence_is_not_a_scenario():
    titles = plan_record_parse.parse_scenarios(_SLICE)
    assert "inside a doc string" not in titles
    assert "y" not in titles


def test_scenarios_skip_a_non_gherkin_fence_before_the_gherkin_one():
    text = "```bash\nScenario: shell\n```\n```gherkin\nScenario: real\n```\n"
    assert plan_record_parse.parse_scenarios(text) == ["real"]


def test_a_one_line_doc_string_does_not_hide_the_next_scenario():
    text = '```gherkin\nGiven """one line"""\nScenario: after\n```\n'
    assert plan_record_parse.parse_scenarios(text) == ["after"]


def test_scenario_comment_lines_are_not_scenarios():
    assert plan_record_parse.parse_scenarios("```gherkin\n# Scenario: no\n```\n") == []


def test_step_ids_skip_headings_inside_a_fence():
    assert plan_record_parse.parse_step_ids(_SLICE) == ["1.1", "1.2", "1.3"]


@pytest.mark.parametrize("text", ["", "# Plan: only a title\n", "### Slice 1: x\n"])
def test_a_slice_without_gherkin_or_steps_reads_as_empty(text):
    assert plan_record_parse.parse_scenarios(text) == []
    assert plan_record_parse.parse_step_ids(text) == []


# ---------------------------------------------------------------------------
# parse_build_progress
# ---------------------------------------------------------------------------


def _progress(text: str) -> dict:
    return plan_record_parse.parse_build_progress(text)


def test_progress_reads_unindented_slice_lines_and_not_indented_steps():
    md = """## Build Progress

#### Wave 1
- [ ] Slice 1: Parse
  - [x] Step 1.1: nested
- [x] Slice 2: Build
  - [ ] Step 2.1: nested
"""
    assert _progress(md) == {
        "legacy": False,
        "items": [
            {"kind": "slice", "id": "1", "header": "Slice 1: Parse", "done": False},
            {"kind": "slice", "id": "2", "header": "Slice 2: Build", "done": True},
        ],
    }


def test_progress_reads_unindented_steps_with_and_without_a_step_prefix():
    md = "## Build Progress\n- [x] Step 1.1: Parse it\n- [ ] Just a header\n"
    assert _progress(md)["items"] == [
        {"kind": "step", "id": "1.1", "header": "Parse it", "done": True},
        {
            "kind": "step",
            "id": "Just a header",
            "header": "Just a header",
            "done": False,
        },
    ]


def test_progress_skips_the_acceptance_criteria_mirror_until_the_next_h3():
    md = """## Build Progress

### Acceptance Criteria
- [ ] mirrored criterion

### Slices
- [ ] Slice 1: Parse

## Risks
- [ ] outside the section
"""
    assert [i["header"] for i in _progress(md)["items"]] == ["Slice 1: Parse"]


def test_progress_ignores_checkboxes_outside_the_section_and_before_it():
    md = "## Acceptance Criteria\n- [ ] AC1 x\n\n## Build Progress\n- [x] Slice 1: a\n"
    assert [i["header"] for i in _progress(md)["items"]] == ["Slice 1: a"]


def test_a_plan_without_a_build_progress_heading_is_scanned_whole_and_marked_legacy():
    md = "- [x] Step 1.1: do thing\n## Acceptance Criteria\n- [ ] AC1 x\n"
    result = _progress(md)
    assert result["legacy"] is True
    assert [i["header"] for i in result["items"]] == ["do thing", "AC1 x"]


@pytest.mark.parametrize("md", ["", "# Plan: only a title\n", "## Build Progress\n"])
def test_a_plan_with_no_checkboxes_has_no_items(md):
    assert _progress(md)["items"] == []
    assert _progress(md)["legacy"] is ("Build Progress" not in md)


def test_the_item_regex_equals_the_guardians_step_pattern():
    pg = _load_progress_guardian()
    assert plan_record_parse._PROGRESS_ITEM_RE.pattern == pg.STEP_PATTERN.pattern


# --- parity with the guardian's own loop ------------------------------------


def _load_progress_guardian():
    scripts = str(_REPO_ROOT / "plugins" / "dev-team" / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import progress_guardian

    return progress_guardian


def _oracle_steps(text: str) -> list[tuple[bool, str]]:
    """A frozen copy of the loop in `progress_guardian.parse_plan` (as of
    #2275), kept here so the parity test stays an oracle after the guardian
    starts reading the record."""
    step_pattern = _load_progress_guardian().STEP_PATTERN
    lines = text.splitlines()
    has_build_progress = any(
        line.rstrip().startswith("## Build Progress") for line in lines
    )
    steps = []
    in_build_progress = not has_build_progress
    in_acceptance = False
    for raw in lines:
        line = raw.rstrip()
        if has_build_progress:
            if line.startswith("## Build Progress"):
                in_build_progress = True
                in_acceptance = False
                continue
            if in_build_progress and line.startswith("## "):
                in_build_progress = False
                continue
            if in_build_progress and line.startswith("### Acceptance Criteria"):
                in_acceptance = True
                continue
            if in_acceptance and line.startswith("### "):
                in_acceptance = False
        if not in_build_progress or in_acceptance:
            continue
        m = step_pattern.match(line)
        if m:
            steps.append((m.group(1).lower() == "x", m.group(2).strip()))
    return steps


def _guardian_fixture_plans() -> list[str]:
    """Every plan literal the guardian's own tests write: string arguments of
    `.write_text(...)` and `make_plan(path, ...)` that fold to a constant."""
    import ast

    source = (
        _REPO_ROOT / "tests" / "scripts" / "test_progress_guardian.py"
    ).read_text()

    def fold(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left, right = fold(node.left), fold(node.right)
            return None if left is None or right is None else left + right
        return None

    plans = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        name = getattr(node.func, "attr", getattr(node.func, "id", ""))
        if name == "write_text":
            candidate = fold(node.args[0])
        elif name == "make_plan" and len(node.args) > 1:
            candidate = fold(node.args[1])
        else:
            continue
        if candidate and "- [" in candidate:
            plans.append(candidate)
    return plans


_NESTED_REAL_SHAPE = """# Plan: real shape

## Acceptance Criteria

- [ ] AC1 x

## Build Progress

This section is the machine-parseable recovery handle.

### Slices (grouped by wave)

#### Wave 1
- [ ] Slice 1: Plan parse helpers
  - [x] Step 1.1: nested one
  - [ ] Step 1.2: nested two
- [x] Slice 2: The record
    - [x] Step 2.1: deeper nested

### Acceptance Criteria
- [ ] mirrored

### Notes
- [x] Step 9.9: after the mirror

## Risks
- [ ] outside
"""


def test_the_fixture_extraction_finds_the_guardians_plans():
    assert len(_guardian_fixture_plans()) >= 20


def test_progress_items_equal_the_guardians_steps_on_every_guardian_fixture_plan():
    plans = [*_guardian_fixture_plans(), _NESTED_REAL_SHAPE]
    for plan in plans:
        got = [(i["done"], i["header"]) for i in _progress(plan)["items"]]
        assert got == _oracle_steps(plan), plan


def test_the_nested_real_shape_plan_yields_only_unindented_items():
    headers = [i["header"] for i in _progress(_NESTED_REAL_SHAPE)["items"]]
    assert headers == [
        "Slice 1: Plan parse helpers",
        "Slice 2: The record",
        "after the mirror",
    ]
