"""Unit tests for scripts/lib/plan_record_parse.py (#2275).

Behavioural: each parser takes plan text and returns plain data.
"""

from __future__ import annotations

import re
import sys
import time

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


@pytest.mark.parametrize(
    ("items", "expected"),
    [
        (["new", "AC1 a", "AC2 b"], ["AC3", "AC1", "AC2"]),
        (["AC2 a", "b"], ["AC2", "AC3"]),
        (["b", "AC1 a"], ["AC2", "AC1"]),
        (["AC1 a", "AC1 b", "AC1 c"], ["AC1", "AC2", "AC3"]),
        (["AC3 a", "AC3 b", "c"], ["AC3", "AC2", "AC4"]),
        (["a", "b", "c"], ["AC1", "AC2", "AC3"]),
    ],
)
def test_prefixed_ids_never_move_and_every_id_is_unique(items, expected):
    md = "## Acceptance Criteria\n" + "".join(f"- [ ] {i}\n" for i in items)
    ids = _ids(md)
    assert ids == expected
    assert len(set(ids)) == len(ids)


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


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("**Covers**: AC1", ["AC1"]),
        ("**Covers:** AC1", ["AC1"]),
        ("**Covers:**   AC3 ,AC5", ["AC3", "AC5"]),
        ("Covers : AC9 and more", ["AC9"]),
        ("**Covers**: AC3, AC5 (both) , prose", ["AC3", "AC5"]),
        ("**Covers**: AC3, AC3", ["AC3"]),
        ("  **Covers**: AC4", ["AC4"]),
    ],
)
def test_covers_line_tolerates_spaces_bold_variants_and_trailing_text(line, expected):
    md = f"#### Step 1.1: a\n{line}\n"
    assert plan_record_parse.parse_covers(md) == {"1.1": expected}


@pytest.mark.parametrize(
    "line",
    ["**Covers**: AC1x", "**Covers**: ac2", "**Covers**: AC", "**Covers**: xAC1"],
)
def test_covers_tokens_must_be_whole_uppercase_ac_ids(line):
    assert plan_record_parse.parse_covers(f"#### Step 1.1: a\n{line}\n") == {}


@pytest.mark.parametrize(
    "heading", ["### Slice 2: next", "## Risks", "# Title", "### Anything"]
)
def test_a_higher_heading_ends_the_step_so_a_later_covers_line_is_not_credited(heading):
    md = f"#### Step 1.1: a\n**Covers**: AC1\n{heading}\n**Covers**: AC2\n"
    assert plan_record_parse.parse_covers(md) == {"1.1": ["AC1"]}


def test_a_fenced_heading_does_not_end_the_step():
    md = "#### Step 1.1: a\n```text\n## Risks\n```\n**Covers**: AC2\n"
    assert plan_record_parse.parse_covers(md) == {"1.1": ["AC2"]}


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


def test_a_step_prefix_makes_a_step_even_when_the_title_starts_with_slice():
    md = "## Build Progress\n- [ ] Step 1.1: Slice 2 cleanup\n- [x] Slice 2: Real slice\n"
    assert _progress(md)["items"] == [
        {"kind": "step", "id": "1.1", "header": "Slice 2 cleanup", "done": False},
        {"kind": "slice", "id": "2", "header": "Slice 2: Real slice", "done": True},
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


# The oracle's own copy of the guardian's line pattern. It is a literal on
# purpose: the oracle must not follow the live guardian when that changes.
_ORACLE_STEP_PATTERN = re.compile(
    r"^-\s+\[(?P<state>[ xX])\]\s+(?:Step\s+[\d.]+:\s+)?(.+)$"
)


def test_the_record_item_pattern_is_the_commit_evidence_pattern():
    import commit_evidence

    assert plan_record_parse._PROGRESS_ITEM_RE is commit_evidence.STEP_PATTERN


def test_the_oracle_pattern_equals_the_records_item_pattern():
    assert _ORACLE_STEP_PATTERN.pattern == plan_record_parse._PROGRESS_ITEM_RE.pattern


def test_tripwire_the_guardians_step_pattern_still_equals_the_oracle_pattern():
    """Fails when `progress_guardian.STEP_PATTERN` changes, so the oracle and
    the record's pattern are revisited on purpose rather than drifting."""
    pg = _load_progress_guardian()
    assert pg.STEP_PATTERN.pattern == _ORACLE_STEP_PATTERN.pattern


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
    step_pattern = _ORACLE_STEP_PATTERN
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


_HAND_WRITTEN_PLANS = {
    "build-progress-without-mirror": (
        "## Build Progress\n\n- [ ] Slice 1: a\n- [X] Step 1.1: upper case\n"
        "\n## Risks\n- [ ] outside\n"
    ),
    "mirror-followed-by-slices": (
        "## Build Progress\n\n### Acceptance Criteria\n- [ ] mirrored\n\n"
        "### Slices\n- [ ] Slice 1: a\n- [x] Slice 2: b\n"
    ),
    "two-build-progress-headings": (
        "## Build Progress\n- [ ] Slice 1: a\n\n## Notes\n- [ ] skipped\n\n"
        "## Build Progress\n- [x] Slice 2: b\n"
    ),
    "nested-real-shape": _NESTED_REAL_SHAPE,
}

_PARITY_PLANS = {
    **{
        f"guardian-fixture-{n}": plan
        for n, plan in enumerate(_guardian_fixture_plans())
    },
    **_HAND_WRITTEN_PLANS,
}


def test_the_parity_set_covers_the_shapes_the_guardian_handles():
    plans = list(_PARITY_PLANS.values())
    guardian = [p for k, p in _PARITY_PLANS.items() if k.startswith("guardian-")]
    assert any("## Build Progress" in p for p in guardian)
    assert any(
        "## Build Progress" in p
        and "### Acceptance Criteria" in p.split("## Build Progress", 1)[1]
        for p in guardian
    )
    assert any("[X]" in p for p in plans)
    assert any("## Build Progress" not in p and "- [" in p for p in guardian)


@pytest.mark.parametrize("plan", list(_PARITY_PLANS.values()), ids=list(_PARITY_PLANS))
def test_progress_items_equal_the_guardians_steps(plan):
    """Same as the guardian's loop as of #2275. Parity, not proof that the
    loop is right: a bug in both would pass."""
    got = [(i["done"], i["header"]) for i in _progress(plan)["items"]]
    assert got == _oracle_steps(plan)


def test_the_nested_real_shape_plan_yields_only_unindented_items():
    headers = [i["header"] for i in _progress(_NESTED_REAL_SHAPE)["items"]]
    assert headers == [
        "Slice 1: Plan parse helpers",
        "Slice 2: The record",
        "after the mirror",
    ]


# ---------------------------------------------------------------------------
# parse_blockers
# ---------------------------------------------------------------------------

_REVIEW = """## Plan Review Summary

Plan tier: standard

**Open blocker**: Slice 2 - missing error path
- **Open blocker**: Slice 3 - second  finding
**Resolved blocker**: Slice 2 - earlier problem
"""


def test_open_and_resolved_blocker_lines_are_read():
    assert plan_record_parse.parse_blockers(_REVIEW) == {
        "open": [
            {"slice": "2", "text": "missing error path"},
            {"slice": "3", "text": "second  finding"},
        ],
        "resolved": [{"slice": "2", "text": "earlier problem"}],
    }


def test_a_resolved_blocker_does_not_cancel_an_open_one_in_the_parser():
    text = (
        "## Plan Review Summary\n"
        "**Open blocker**: Slice 1 - same\n"
        "**Resolved blocker**: Slice 1 - same\n"
    )
    assert plan_record_parse.parse_blockers(text) == {
        "open": [{"slice": "1", "text": "same"}],
        "resolved": [{"slice": "1", "text": "same"}],
    }


@pytest.mark.parametrize(
    "line",
    [
        "**Open blocker**: Slice 4 - gap",
        "**Open blocker:** Slice 4 - gap",
        "**Open blocker** : Slice 4 - gap",
        "- **Open blocker:** Slice 4 - gap",
    ],
)
def test_the_colon_may_sit_inside_or_outside_the_bold(line):
    text = f"## Plan Review Summary\n{line}\n"
    assert plan_record_parse.parse_blockers(text)["open"] == [
        {"slice": "4", "text": "gap"}
    ]


def test_the_resolved_label_also_accepts_the_colon_inside_the_bold():
    text = "## Plan Review Summary\n**Resolved blocker:** Slice 4 - gap\n"
    assert plan_record_parse.parse_blockers(text)["resolved"] == [
        {"slice": "4", "text": "gap"}
    ]


def test_blocker_lines_outside_the_summary_section_are_ignored():
    text = (
        "**Open blocker**: Slice 1 - before\n"
        "## Plan Review Summary\n"
        "## Risks\n"
        "**Open blocker**: Slice 1 - after the section ends\n"
    )
    assert plan_record_parse.parse_blockers(text) == {"open": [], "resolved": []}


def test_a_blocker_line_inside_a_fence_is_ignored():
    text = "## Plan Review Summary\n```text\n**Open blocker**: Slice 1 - fenced\n```\n"
    assert plan_record_parse.parse_blockers(text) == {"open": [], "resolved": []}


@pytest.mark.parametrize(
    "line",
    [
        "**Open blocker**: Slice two - not a number",
        "**Open blocker**: Slice 2 -",
        "**Open blocker**: Slice 2 - ",
        "**Blocker**: Slice 2 - wrong label",
        "Open blocker: Slice 2 - no bold",
        "**Open blocker**: Slice <n> - <text>",
    ],
)
def test_malformed_blocker_lines_are_not_blockers(line):
    text = f"## Plan Review Summary\n{line}\n"
    assert plan_record_parse.parse_blockers(text) == {"open": [], "resolved": []}


# A quadratic pattern needs about 8 s for this input and a linear one a few
# milliseconds, so the 2 s bound separates them without timing noise.
_LONG_RUN = 50_000
_LINEAR_BOUND_SECONDS = 2.0


@pytest.mark.parametrize(
    "line",
    [
        "**Open blocker**: Slice 1 - a" + " " * _LONG_RUN + "b",
        "**Open blocker**: Slice 1 - a" + " " * _LONG_RUN,
        "**Open blocker**: Slice 1" + " " * _LONG_RUN,
        "**Open blocker**:" + " " * _LONG_RUN + "Slice 1 -",
    ],
    ids=["inner-spaces", "trailing-spaces", "no-dash", "leading-spaces"],
)
def test_a_blocker_line_with_a_long_run_of_spaces_parses_in_linear_time(line):
    started = time.perf_counter()
    plan_record_parse.parse_blockers(f"## Plan Review Summary\n{line}\n")
    assert time.perf_counter() - started < _LINEAR_BOUND_SECONDS


def test_a_blocker_keeps_inner_spaces_and_drops_the_outer_ones():
    text = "## Plan Review Summary\n   **Open blocker**: Slice 1 - a   b   \n"
    assert plan_record_parse.parse_blockers(text)["open"] == [
        {"slice": "1", "text": "a   b"}
    ]


@pytest.mark.parametrize(
    "text", ["", "# Plan: only a title\n", "## Plan Review Summary\n"]
)
def test_a_plan_with_no_blockers_reads_as_none_open_and_none_resolved(text):
    assert plan_record_parse.parse_blockers(text) == {"open": [], "resolved": []}


# --- the template documents the conventions ---------------------------------

_TEMPLATE = (
    _REPO_ROOT
    / "plugins"
    / "dev-team"
    / "skills"
    / "plan"
    / "references"
    / "plan-template.md"
)


def _template_as_a_plan() -> str:
    """The template body between its outer four-backtick fence."""
    lines = _TEMPLATE.read_text().splitlines()
    start = lines.index("````markdown") + 1
    end = len(lines) - 1 - lines[::-1].index("````")
    return "\n".join(lines[start:end])


@pytest.mark.parametrize(
    "producer", ["**Covers**:", "**Open blocker**:", "**Resolved blocker**:"]
)
def test_the_plan_template_shows_each_convention_line(producer):
    assert producer in _TEMPLATE.read_text()


def test_the_template_placeholders_do_not_opt_a_new_plan_in():
    plan = _template_as_a_plan()
    assert "**Covers**:" in plan
    assert "**Open blocker**:" in plan
    assert plan_record_parse.parse_covers(plan) == {}
    assert plan_record_parse.parse_blockers(plan) == {"open": [], "resolved": []}
