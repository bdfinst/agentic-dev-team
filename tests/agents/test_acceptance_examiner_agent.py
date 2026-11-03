"""Prose-contract tests for the source-blind acceptance-examiner agent
(issue #2270, plan slice 2).

The agent file is the examiner's whole prompt. These tests pin the text the
model follows: tool grant, the Allowed/Forbidden/Indeterminate sections, and
the output schema the SubagentStop recorder parses. They do not test runtime
behavior beyond loading the review roster. The registration group at the
end pins the registry, classification, agent-docs and roster entries.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

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


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("name", "acceptance-examiner"),
        ("tools", "Bash"),
        ("model", "opus"),
        ("effort", "high"),
        ("color", "cyan"),
    ],
)
def test_frontmatter_field_has_the_contracted_value(field: str, expected: str) -> None:
    fm, _ = frontmatter_and_body(AGENT)
    assert frontmatter_field(fm, field) == expected


def test_description_names_dispatcher_without_colon() -> None:
    fm, _ = frontmatter_and_body(AGENT)
    description = frontmatter_field(fm, "description")
    assert "/build Step 7.6" in description
    assert ":" not in description


@pytest.mark.parametrize(
    "phrase",
    [
        "AC1",
        "Gherkin",
        "run commands",
        "working directory",
        "Acceptance-examination plan: <id>",
    ],
)
def test_what_you_receive_names_input_or_marker(phrase: str) -> None:
    assert phrase in _section("What you receive")


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


@pytest.mark.parametrize("phrase", ["by pattern", "false positive", "SubagentStop"])
def test_forbidden_section_says_detection_may_be_false_positive(phrase: str) -> None:
    assert phrase in _section("Forbidden")


@pytest.mark.parametrize(
    "phrase",
    [
        "judge from the output only",
        "never infer from source",
        "do not explore the repository",
    ],
)
def test_how_to_examine_forbids_inferring_from_source_and_exploring(
    phrase: str,
) -> None:
    assert phrase in _section("How to examine").lower()


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


@pytest.mark.parametrize(
    "phrase",
    [
        "one complete segment of a Bash call you made",
        "whitespace-normalized",
        "leading `cd <dir> &&` removed",
        "`2>&1`",
    ],
)
def test_output_prose_states_how_command_is_matched_to_a_bash_call(phrase: str) -> None:
    _, prose = _output_block_and_prose()
    assert phrase in prose


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


# --------------------------------------------------------------------------
# Registration: registry, classification, agent docs, roster
# --------------------------------------------------------------------------

KNOWLEDGE = REPO_ROOT / "plugins" / "dev-team" / "knowledge"
REGISTRY = KNOWLEDGE / "agent-registry.md"
CLASSIFICATION = KNOWLEDGE / "review-lens-classification.md"
AGENT_INFO = REPO_ROOT / "plugins" / "dev-team" / "docs" / "agent_info.md"
ROSTER = REPO_ROOT / "plugins" / "dev-team" / "scripts" / "lib" / "review_roster.py"


def _table_row(path: Path, row_key: str) -> dict[str, str]:
    """The one table row whose first cell is `row_key`, keyed by header."""
    lines = path.read_text(encoding="utf-8").splitlines()
    rows = [i for i, line in enumerate(lines) if line.startswith(f"| {row_key} |")]
    assert len(rows) == 1, f"{path.name}: expected one row for {row_key}, got {rows}"
    header_at = max(i for i in range(rows[0]) if lines[i + 1].startswith("| ---"))
    cells = lambda line: [c.strip() for c in line.strip().strip("|").split("|")]
    return dict(zip(cells(lines[header_at]), cells(lines[rows[0]]), strict=True))


def test_registry_row_says_dispatched_by_build_step_7_6_never_directly() -> None:
    row = _table_row(REGISTRY, "acceptance-examiner")
    assert row["File"] == "`agents/acceptance-examiner.md`"
    assert "`/build` Step 7.6" in row["What It Checks"]
    assert "never directly" in row["What It Checks"]


def test_classification_row_is_a_verification_gate() -> None:
    assert (
        _table_row(CLASSIFICATION, "acceptance-examiner")["Class"]
        == "verification-gate"
    )


def test_agent_docs_row_names_the_file_and_model() -> None:
    row = _table_row(AGENT_INFO, "`acceptance-examiner`")
    assert "acceptance-examiner.md" in row["File"]
    assert row["Model"] == "opus"


def test_review_roster_lists_the_examiner_as_a_non_review_agent() -> None:
    sys.path.insert(0, str(ROSTER.parent))
    import review_roster

    assert "acceptance-examiner" in review_roster.NON_REVIEW_AGENTS
