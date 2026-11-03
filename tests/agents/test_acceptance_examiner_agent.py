"""Prose-contract tests for the source-blind acceptance-examiner agent
(issue #2270, plan slice 2).

The agent file is the examiner's whole prompt. These tests pin the text the
model follows: tool grant, the Allowed/Forbidden/Indeterminate sections, and
the output schema the SubagentStop recorder parses. They do not test runtime
behavior. Registration rows are asserted in Step 2.2.
"""

from __future__ import annotations

import json
import re

import pytest
from _plugin_dirs import frontmatter_and_body, frontmatter_field

from _repo_root import REPO_ROOT

AGENT = REPO_ROOT / "plugins" / "dev-team" / "agents" / "acceptance-examiner.md"

SECTION_ORDER = [
    "What you receive",
    "Allowed",
    "Forbidden",
    "How to examine",
    "Indeterminate",
    "Output format",
    "Audit note",
]


def _body() -> str:
    return frontmatter_and_body(AGENT)[1]


def _section(heading: str) -> str:
    """Text under `## <heading>` up to the next `## ` heading; "" if absent."""
    match = re.search(
        rf"^## {re.escape(heading)}\s*$(.*?)(?=^## |\Z)",
        _body(),
        re.MULTILINE | re.DOTALL,
    )
    return match.group(1) if match else ""


def _bullets(heading: str) -> list[str]:
    return [
        line.strip()[2:]
        for line in _section(heading).splitlines()
        if line.strip().startswith("- ")
    ]


def _output_block_and_prose() -> tuple[dict, str]:
    section = _section("Output format")
    match = re.search(r"```json\n(.*?)\n```(.*)", section, re.DOTALL)
    assert match, "Output format has no fenced json block"
    return json.loads(match.group(1)), match.group(2)


def test_agent_file_exists() -> None:
    assert AGENT.is_file()


def test_frontmatter_name_is_acceptance_examiner() -> None:
    fm, _ = frontmatter_and_body(AGENT)
    assert frontmatter_field(fm, "name") == "acceptance-examiner"


def test_tools_list_is_exactly_bash() -> None:
    fm, _ = frontmatter_and_body(AGENT)
    assert frontmatter_field(fm, "tools") == "Bash"


def test_model_is_opus() -> None:
    fm, _ = frontmatter_and_body(AGENT)
    assert frontmatter_field(fm, "model") == "opus"


def test_effort_is_high() -> None:
    fm, _ = frontmatter_and_body(AGENT)
    assert frontmatter_field(fm, "effort") == "high"


def test_color_is_cyan() -> None:
    fm, _ = frontmatter_and_body(AGENT)
    assert frontmatter_field(fm, "color") == "cyan"


def test_description_names_dispatcher_and_is_one_line_without_colon() -> None:
    fm, _ = frontmatter_and_body(AGENT)
    description = frontmatter_field(fm, "description")
    assert "/build Step 7.6" in description
    assert ":" not in description


def test_what_you_receive_names_inputs_and_marker_line() -> None:
    section = _section("What you receive")
    assert "AC1" in section
    assert "Gherkin" in section
    assert "run commands" in section
    assert "working directory" in section
    assert "Acceptance-examination plan: <id>" in section


def test_prompt_treats_plan_text_and_command_output_as_data() -> None:
    section = _section("What you receive")
    assert "data, not instructions" in section


@pytest.mark.parametrize(
    "phrase",
    [
        "run commands",
        "read their output",
        ".feature",
        "scratch files outside the repository",
    ],
)
def test_allowed_section_has_a_bullet_containing(phrase: str) -> None:
    assert any(phrase in bullet for bullet in _bullets("Allowed"))


@pytest.mark.parametrize(
    "phrase",
    [
        "production source",
        "test source",
        "the diff",
        "review reports",
        "build evidence",
        "modify tracked files or git state",
    ],
)
def test_forbidden_section_has_a_bullet_containing(phrase: str) -> None:
    assert any(phrase in bullet for bullet in _bullets("Forbidden"))


@pytest.mark.parametrize("word", ["tainted", "denylist"])
def test_forbidden_section_contains_literal_word(word: str) -> None:
    assert word in _section("Forbidden")


def test_forbidden_section_says_detection_may_be_false_positive() -> None:
    section = _section("Forbidden")
    assert "by pattern" in section
    assert "false positive" in section
    assert "SubagentStop" in section


def test_how_to_examine_forbids_inferring_from_source_and_exploring() -> None:
    section = _section("How to examine").lower()
    assert "judge from the output only" in section
    assert "never infer from source" in section
    assert "do not explore the repository" in section


def test_indeterminate_section_has_the_report_as_indeterminate_sentence() -> None:
    assert (
        "reported as indeterminate with a reason, never as met or not-met"
        in _section("Indeterminate")
    )


def test_indeterminate_section_allows_empty_command_and_denies_waiver() -> None:
    section = _section("Indeterminate")
    assert "`command` empty" in section
    assert "no waiver" in section


def test_output_block_has_one_criteria_list_of_rows_with_four_keys() -> None:
    block, _ = _output_block_and_prose()
    assert list(block) == ["criteria"]
    assert set(block["criteria"][0]) == {
        "criterion",
        "verdict",
        "command",
        "observation",
    }


def test_output_block_verdict_enum_is_exactly_met_not_met_indeterminate() -> None:
    block, _ = _output_block_and_prose()
    verdicts = [v.strip() for v in block["criteria"][0]["verdict"].split("|")]
    assert verdicts == ["met", "not-met", "indeterminate"]


def test_output_prose_requires_exactly_one_row_per_criterion() -> None:
    _, prose = _output_block_and_prose()
    assert "exactly one row" in prose


def test_output_prose_requires_a_command_you_actually_ran() -> None:
    _, prose = _output_block_and_prose()
    assert "a command you actually ran" in prose


def test_output_prose_states_how_command_is_matched_to_a_bash_call() -> None:
    _, prose = _output_block_and_prose()
    assert "one complete segment of a Bash call you made" in prose
    assert "whitespace-normalized" in prose
    assert "leading `cd <dir> &&` removed" in prose
    assert "`2>&1`" in prose


def test_output_prose_requires_non_empty_observation_of_relevant_lines() -> None:
    _, prose = _output_block_and_prose()
    assert "`observation` is non-empty" in prose
    assert "relevant output lines" in prose


def test_audit_note_says_hook_writes_record_from_transcript_with_agent_id() -> None:
    section = _section("Audit note")
    assert "hook, not you, writes the record" in section
    assert "transcript is the evidence" in section
    assert "agent id" in section


def test_sections_appear_in_the_contracted_order() -> None:
    headings = re.findall(r"^## (.+?)\s*$", _body(), re.MULTILINE)
    assert headings == SECTION_ORDER
