"""#2271 slice 3 — the plan-review-acceptance critic judges each scenario's
falsifier (`# Still passes if: <change>`). The script `plan_falsifiers.py`
decides absence; the critic (read-only, no Bash) judges quality and reports
when the list is unavailable.

These tests verify authored agent text, not runtime behavior.
"""

from __future__ import annotations

import re
from itertools import pairwise

import pytest

from _repo_root import REPO_ROOT

AGENT = REPO_ROOT / "plugins" / "dev-team" / "agents" / "plan-review-acceptance.md"

SCRIPT = "plan_falsifiers.py"
RUBRIC = "plan-review-rubric.md"
ISSUE_PREFIX = "Falsifier:"

BLOCKER_NOT_SUPPLIED = (
    "Falsifier: list unavailable (plan_falsifiers.py output not supplied)"
)
BLOCKER_ERROR = "Falsifier: list unavailable: <error>"
BLOCKER_NOT_SCANNED = "Falsifier: slice <id> not scanned"

KILLER_THEN = '"lists each scenario with its falsifier text"'
KILLER_FALSIFIER = '"the script reports only presence"'
TAUTOLOGY_THEN = '"the response is not empty"'
TAUTOLOGY_FALSIFIER = '"the handler returns a fixed string"'


def _text() -> str:
    return AGENT.read_text(encoding="utf-8")


def _section(heading: str, level: str = "##") -> str:
    """Body of the `heading` section, up to the next heading of the same or higher level."""
    text = _text()
    marker = f"{level} {heading}\n"
    assert marker in text, f"missing heading: {marker!r}"
    body = text.split(marker, 1)[1]
    stop = re.search(rf"^#{{1,{len(level)}}} ", body, re.MULTILINE)
    return body[: stop.start()] if stop else body


def _bdd_section() -> str:
    return _section("BDD Scenario Quality", level="###")


def _falsifier_item() -> str:
    match = re.search(
        r"^6\. \*\*Falsifier\*\* — .*?(?=^\d+\. \*\*|\Z)",
        _bdd_section(),
        re.MULTILINE | re.DOTALL,
    )
    assert match, "no item 6 '**Falsifier** —' under BDD Scenario Quality"
    return match.group(0)


def _severity_lines() -> list[str]:
    return [
        line
        for line in _section("Severity rules").splitlines()
        if line.startswith("- ")
    ]


def _line_matching(lines: list[str], pattern: str) -> str:
    hits = [line for line in lines if re.search(pattern, line, re.IGNORECASE)]
    assert len(hits) == 1, f"expected exactly one line matching {pattern!r}, got {hits}"
    return hits[0]


def test_frontmatter_declares_name_model_effort() -> None:
    text = _text()
    assert text.splitlines()[0] == "---"
    frontmatter = text.split("---", 2)[1]
    assert "name: plan-review-acceptance" in frontmatter
    assert "model: sonnet" in frontmatter
    assert "effort: high" in frontmatter


def test_critic_stays_read_only_without_bash() -> None:
    frontmatter = _text().split("---", 2)[1]
    assert "tools: Read, Grep, Glob\n" in frontmatter


def test_rubric_file_is_still_cited() -> None:
    assert RUBRIC in _text()


def test_falsifier_is_item_six_under_bdd_scenario_quality() -> None:
    assert _falsifier_item().startswith("6. **Falsifier** — ")


def test_falsifier_item_requires_marker_as_first_line_under_title() -> None:
    item = _falsifier_item()
    assert "# Still passes if: <change>" in item
    assert "first line under its title" in item


def test_what_you_receive_names_script_output_and_its_fields() -> None:
    receive = _section("What you receive")
    assert SCRIPT in receive
    for field in ("scenarios", "missing", "scanned_slices", "skipped_slices", "error"):
        assert f"`{field}`" in receive, field


def test_missing_array_is_authoritative_for_absence() -> None:
    item = _falsifier_item()
    assert "authoritative" in item
    assert "`missing`" in item


def test_findings_use_the_falsifier_issue_prefix() -> None:
    item = _falsifier_item()
    assert ISSUE_PREFIX in item
    assert "scenario_issues" in item


@pytest.mark.parametrize(
    "blocker",
    [BLOCKER_NOT_SUPPLIED, BLOCKER_ERROR, BLOCKER_NOT_SCANNED],
    ids=["output-not-supplied", "error-set", "slice-not-scanned"],
)
def test_unavailability_blocker_is_spelled_out(blocker: str) -> None:
    assert blocker in _falsifier_item()


def test_not_scanned_blocker_names_both_slice_lists() -> None:
    sentence = _line_with(_falsifier_item(), BLOCKER_NOT_SCANNED)
    assert "`scanned_slices`" in sentence
    assert "`skipped_slices`" in sentence


def _line_with(block: str, needle: str) -> str:
    sentences = re.split(r"(?<=\.)\s+", " ".join(block.split()))
    hits = [s for s in sentences if needle in s]
    assert hits, f"no sentence contains {needle!r}"
    return hits[0]


def test_critic_is_told_it_has_no_bash_tool() -> None:
    assert "no Bash tool" in _falsifier_item()


def test_no_sentence_instructs_the_critic_to_run_the_script() -> None:
    sentences = re.split(r"(?<=\.)\s+", " ".join(_text().split()))
    offenders = [
        s
        for s in sentences
        if re.search(r"run .*plan_falsifiers\.py", s, re.IGNORECASE)
    ]
    assert offenders == []


def test_missing_or_empty_falsifier_is_a_blocker_on_one_line() -> None:
    line = _line_matching(_severity_lines(), r"missing.*falsifier.*blocker")
    assert "empty" in line.lower()


def test_killer_falsifier_is_a_warning_not_a_blocker_on_one_line() -> None:
    line = _line_matching(_severity_lines(), r"killer.*falsifier.*warning")
    assert "blocker" not in line.lower()
    assert "contradicts a `Then` clause" in line


def test_tautological_falsifier_is_a_warning_not_a_blocker_on_one_line() -> None:
    line = _line_matching(_severity_lines(), r"tautological.*falsifier.*warning")
    assert "blocker" not in line.lower()
    assert "constant or stub" in line


def test_unavailable_falsifier_list_is_a_blocker_on_one_line() -> None:
    line = _line_matching(_severity_lines(), r"falsifier list unavailable.*blocker")
    assert "not scanned" in line


def _pair_is_adjacent(then_text: str, falsifier_text: str) -> bool:
    lines = _falsifier_item().splitlines()
    for first, second in pairwise(lines):
        if then_text in first and falsifier_text in second:
            return first.startswith("   ") and second.startswith("   ")
    return False


def test_killer_example_is_an_indented_then_falsifier_pair() -> None:
    assert _pair_is_adjacent(KILLER_THEN, KILLER_FALSIFIER)


def test_tautological_example_is_an_indented_then_falsifier_pair() -> None:
    assert _pair_is_adjacent(TAUTOLOGY_THEN, TAUTOLOGY_FALSIFIER)


def test_tautological_fix_names_a_sharper_then() -> None:
    assert "sharper `Then`" in _falsifier_item()
