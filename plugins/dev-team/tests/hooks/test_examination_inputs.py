"""Unit tests for hooks/lib/examination_inputs.py (#2270, Step 1.1)."""

from __future__ import annotations

import sys

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_PLUGIN_DIR = _REPO_ROOT / "plugins" / "dev-team"
_LIB_DIR = _PLUGIN_DIR / "hooks" / "lib"

if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import examination_inputs as ei  # type: ignore[import-not-found]


def _plan_with_ac(body: str) -> str:
    return f"# Plan\n\n## Acceptance Criteria\n\n{body}\n"


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        pytest.param(
            "prose line\n- [ ] a\n- [x] b\n\n## Next\n\n- [ ] c",
            ["a", "b"],
            id="stops-at-next-h2",
        ),
        pytest.param(
            "- [ ] a\n\n### Notes\n\n- [ ] c",
            ["a"],
            id="skips-subheading-and-its-items",
        ),
        pytest.param("- [ ] a\n  - [ ] sub", ["a"], id="skips-indented-subitem"),
        pytest.param("- [X] a", ["a"], id="uppercase-x"),
        pytest.param(
            "```\n## Fake\n- [ ] x\n```\n- [ ] a",
            ["a"],
            id="ignores-fenced-block",
        ),
    ],
)
def test_criteria_boundary_shapes(body, expected):
    assert ei.plan_examination_inputs(_plan_with_ac(body)).criteria == expected


def test_criteria_empty_when_no_acceptance_heading():
    plan = "# Plan\n\n## Other\n\n- [ ] a\n"
    assert ei.plan_examination_inputs(plan).criteria == []


_PLAN_WITH_GHERKIN_AND_GATE = """\
# Plan

## Slices

### Slice 1

```gherkin
Feature: One
  Scenario: first
```

Prose between.

```python
print("not gherkin")
```

```gherkin
Feature: Two
```

## Pre-PR Quality Gate

- [ ] Tests pass: `pytest -q`
- [ ] `/code-review` passes
- [ ] Linter: `ruff check .`
"""


def test_inputs_include_both_gherkin_blocks_in_document_order():
    inputs = ei.plan_examination_inputs(_PLAN_WITH_GHERKIN_AND_GATE)
    assert inputs.gherkin == [
        "Feature: One\n  Scenario: first",
        "Feature: Two",
    ]


def test_inputs_run_commands_exclude_skill_names():
    inputs = ei.plan_examination_inputs(_PLAN_WITH_GHERKIN_AND_GATE)
    assert inputs.run_commands == ["pytest -q", "ruff check ."]


def test_gherkin_outside_slices_section_is_ignored():
    plan = "## Elsewhere\n\n```gherkin\nFeature: X\n```\n"
    assert ei.plan_examination_inputs(plan).gherkin == []


_DIGEST_PLAN = """\
# Plan

**Status**: in progress

## Acceptance Criteria

- [ ] AC one
- [ ] AC two

## Slices

```gherkin
Feature: One
  Given a step
```

## Pre-PR Quality Gate

- [ ] Tests: `pytest -q`

## Build Progress

- [ ] Step 1.1: do it
"""


def _digest(plan: str) -> str:
    return ei.inputs_digest(ei.plan_examination_inputs(plan))


def _tick_all(plan: str, heading: str) -> str:
    out, active = [], False
    for line in plan.splitlines():
        if line.startswith("## "):
            active = line == heading
        out.append(line.replace("- [ ]", "- [x]") if active else line)
    return "\n".join(out) + "\n"


@pytest.mark.parametrize(
    "edit",
    [
        pytest.param(
            lambda p: p.replace("in progress", "done"), id="status-line-changed"
        ),
        pytest.param(
            lambda p: _tick_all(p, "## Acceptance Criteria"), id="criteria-ticked"
        ),
        pytest.param(
            lambda p: _tick_all(p, "## Pre-PR Quality Gate"), id="gate-ticked"
        ),
        pytest.param(
            lambda p: _tick_all(p, "## Build Progress"), id="build-progress-ticked"
        ),
        pytest.param(
            lambda p: p + "\n## Acceptance Examination\n\n- [ ] AC1 met\n",
            id="examination-section-appended",
        ),
    ],
)
def test_build_edits_do_not_change_digest(edit):
    assert _digest(edit(_DIGEST_PLAN)) == _digest(_DIGEST_PLAN)


@pytest.mark.parametrize(
    "edit",
    [
        pytest.param(lambda p: p.replace("AC two", "AC 2"), id="criterion-text"),
        pytest.param(lambda p: p.replace("a step", "another step"), id="gherkin-step"),
        pytest.param(lambda p: p.replace("pytest -q", "pytest -x"), id="run-command"),
    ],
)
def test_input_edits_change_digest(edit):
    assert _digest(edit(_DIGEST_PLAN)) != _digest(_DIGEST_PLAN)


def test_digest_is_sha256_hex():
    digest = _digest(_DIGEST_PLAN)
    assert len(digest) == 64 and int(digest, 16) >= 0


def test_digest_distinguishes_list_membership():
    moved = ei.ExaminationInputs(criteria=["x"], gherkin=[], run_commands=[])
    other = ei.ExaminationInputs(criteria=[], gherkin=["x"], run_commands=[])
    assert ei.inputs_digest(moved) != ei.inputs_digest(other)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param(
            "Acceptance-examination plan: plans/x.md", "plans/x.md", id="plain"
        ),
        pytest.param(
            "intro\r\nAcceptance-examination plan: plans/x.md   \r\nmore\r\n",
            "plans/x.md",
            id="trailing-spaces-and-crlf",
        ),
        pytest.param("Acceptance-examination plan:   ", None, id="empty-path"),
        pytest.param(
            "Acceptance-examination plan: plans/a.md\n"
            "Acceptance-examination plan: plans/b.md",
            "plans/a.md",
            id="first-marker-wins",
        ),
        pytest.param(
            "Acceptance-examination plan: ../outside/x.md", None, id="parent-segment"
        ),
        pytest.param(
            "Acceptance-examination plan: plans/../../x.md", None, id="nested-parent"
        ),
        pytest.param("no marker here", None, id="absent"),
    ],
)
def test_parse_plan_marker(text, expected):
    assert ei.parse_plan_marker(text) == expected


def test_marker_allows_dotted_names_that_are_not_parent_segments():
    assert (
        ei.parse_plan_marker("Acceptance-examination plan: plans/a..b.md")
        == "plans/a..b.md"
    )


def test_plan_marker_prefix_value():
    assert ei.PLAN_MARKER_PREFIX == "Acceptance-examination plan: "


def test_render_inputs_lists_numbered_criteria_gherkin_commands_and_marker():
    inputs = ei.plan_examination_inputs(
        _PLAN_WITH_GHERKIN_AND_GATE.replace(
            "## Slices",
            "## Acceptance Criteria\n\n- [ ] first\n- [ ] second\n\n## Slices",
        )
    )
    lines = ei.render_inputs(inputs, "plans/x.md").splitlines()
    assert lines[:2] == ["AC1: first", "AC2: second"]
    assert "Feature: One" in lines and "Feature: Two" in lines
    assert "- pytest -q" in lines and "- ruff check ." in lines
    assert lines[-1] == "Acceptance-examination plan: plans/x.md"


def test_rendered_block_round_trips_through_marker_parser():
    rendered = ei.render_inputs(ei.ExaminationInputs(), "plans/x.md")
    assert ei.parse_plan_marker(rendered) == "plans/x.md"


def test_exempt_when_header_declares_not_applicable():
    plan = "# Plan\n\n**Examination**: not-applicable\n\n## Goal\n"
    assert ei.is_exempt(plan) is True


def test_not_exempt_without_the_field():
    assert ei.is_exempt("# Plan\n\n**Status**: draft\n\n## Goal\n") is False


def test_field_after_first_h2_does_not_exempt():
    plan = "# Plan\n\n## Goal\n\n**Examination**: not-applicable\n"
    assert ei.is_exempt(plan) is False


_AC_HEADING = "## Acceptance Criteria"
_MIRROR_PLAN = """\
# Plan

## Acceptance Criteria

- [ ] AC one
- [x] AC two

## Build Progress

### Acceptance Criteria

- [ ] AC one
- [x] AC two

### Slices

- [ ] Step 1.1: do the work
"""


def _guardian_parse(text: str, tmp_path):
    scripts_dir = str(_PLUGIN_DIR / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import progress_guardian  # type: ignore[import-not-found]

    plan = tmp_path / "plan.md"
    plan.write_text(text, encoding="utf-8")
    steps, _errors = progress_guardian.parse_plan(plan)
    return [step.header for step in steps]


def _ac_section_only(plan_text: str) -> str:
    """The plan reduced to its AC section: a legacy (no Build Progress) plan,
    on which `parse_plan` scans every checkbox line."""
    kept, active = [], False
    for line in plan_text.splitlines():
        if line.startswith("## "):
            active = line.rstrip() == _AC_HEADING
        if active:
            kept.append(line)
    return "\n".join(kept) + "\n"


def test_parser_agrees_with_progress_guardian_on_inline_ac_section(tmp_path):
    guardian = _guardian_parse(_ac_section_only(_MIRROR_PLAN), tmp_path)
    ours = ei.plan_examination_inputs(_MIRROR_PLAN).criteria
    assert ours == guardian == ["AC one", "AC two"]


def test_both_parsers_exclude_the_build_progress_mirror(tmp_path):
    ours = ei.plan_examination_inputs(_MIRROR_PLAN).criteria
    guardian = _guardian_parse(_MIRROR_PLAN, tmp_path)
    assert ours == ["AC one", "AC two"]
    assert guardian == ["do the work"]


_REPO_PLANS = sorted((_REPO_ROOT / "plans").glob("*.md"))


@pytest.mark.skipif(not _REPO_PLANS, reason="no plans/*.md at the repo root")
@pytest.mark.parametrize("plan_path", _REPO_PLANS, ids=lambda p: p.name)
def test_parser_agrees_with_progress_guardian_on_repo_plans(plan_path, tmp_path):
    text = plan_path.read_text(encoding="utf-8")
    ours = ei.plan_examination_inputs(text).criteria
    section = _ac_section_only(text)
    if not ours:
        pytest.skip("plan has no acceptance-criteria checkboxes")
    assert _guardian_parse(section, tmp_path) == ours
