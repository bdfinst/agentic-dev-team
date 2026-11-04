"""Content pins for skills/lane/SKILL.md (issue #2274, Slice 4).

The lane skill is prose over a real tool, so the pins that matter are the ones
that tie the prose to the tool: the refusal table is checked against
`lane_core.REFUSALS`, and the commands are checked against the real argparse
parser. Wording pins cover the flow and the facts a reader acts on.
"""

from __future__ import annotations

import argparse
import re
import sys

import pytest
from skill_doc_helpers import PLUGIN_ROOT, frontmatter, section

SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import lane
from lane_core import REFUSALS

LANE_SKILL = PLUGIN_ROOT / "skills" / "lane" / "SKILL.md"
LANE_COMMAND = '"${CLAUDE_PLUGIN_ROOT}/scripts/lane.py"'
TABLE_ROW = re.compile(r"^\|\s*`(?P<what>[^`]+)`\s*\|")


@pytest.fixture(scope="module")
def lane_text() -> str:
    return LANE_SKILL.read_text()


@pytest.fixture(scope="module")
def refusal_table_whats(lane_text: str) -> list[str]:
    refusals = section(lane_text, r"^## Refusals$", boundary_pattern=r"^## ")
    return [
        match["what"]
        for line in refusals.splitlines()
        if (match := TABLE_ROW.match(line))
    ]


def step_3(text: str) -> str:
    return section(text, r"^### 3\. ", boundary_pattern=r"^### 4\. ")


def test_frontmatter_names_a_user_invocable_worker(lane_text: str) -> None:
    head = frontmatter(lane_text)
    assert re.search(r"^name: lane$", head, re.MULTILINE)
    assert re.search(r"^role: worker$", head, re.MULTILINE)
    assert re.search(r"^user-invocable: true$", head, re.MULTILINE)


def test_allowed_tools_grant_covers_the_lane_script_and_git(lane_text: str) -> None:
    grant = re.search(r"^allowed-tools: (.*)$", frontmatter(lane_text), re.MULTILINE)
    assert grant is not None
    assert f"python3 {LANE_COMMAND} *" in grant[1]
    assert "git *" in grant[1]


def test_description_has_no_colon(lane_text: str) -> None:
    description = re.search(
        r"^description: (.*)$", frontmatter(lane_text), re.MULTILINE
    )
    assert description is not None
    assert ":" not in description[1]


def test_body_declares_the_worker_role_after_the_h1(lane_text: str) -> None:
    assert re.search(r"^# Lane\n\nRole: worker\.", lane_text, re.MULTILINE)


@pytest.mark.parametrize("command", sorted(lane.COMMANDS))
def test_each_command_is_shown_with_the_plugin_root_script(
    lane_text: str, command: str
) -> None:
    assert f"python3 {LANE_COMMAND} {command}" in lane_text


def test_the_skill_documents_exactly_the_tools_commands(lane_text: str) -> None:
    shown = set(re.findall(rf"python3 {re.escape(LANE_COMMAND)} (\w+)", lane_text))
    assert shown == set(lane.COMMANDS)


@pytest.mark.parametrize("flag", ["--expected-trunk", "--expected-tree"])
def test_integrate_example_passes_the_identity_flags(lane_text: str, flag: str) -> None:
    assert flag in step_3(lane_text)


def real_flags() -> set[str]:
    flags: set[str] = set()
    for command in lane.COMMANDS.values():
        parser = argparse.ArgumentParser()
        command.configure(parser)
        flags.update(opt for action in parser._actions for opt in action.option_strings)
    flags.discard("-h")
    flags.discard("--help")
    return flags


def test_documented_flags_are_exactly_the_tools_flags(lane_text: str) -> None:
    arguments = section(lane_text, r"^## Arguments$", boundary_pattern=r"^## Steps$")
    assert set(re.findall(r"--[a-z][a-z-]*", arguments)) == real_flags()


def test_the_flow_lists_the_steps_in_order(lane_text: str) -> None:
    flow = re.search(
        r"The flow in a repository without PRs:\n\n((?:\d\. .*\n)+)", lane_text
    )
    assert flow is not None
    steps = flow[1].splitlines()
    markers = [
        "`open`",
        "Work",
        "`git fetch`",
        "`compose`",
        "`/code-review --since <trunk>` inside the lane",
        "`integrate`",
    ]
    assert len(steps) == len(markers)
    for step, marker in zip(steps, markers, strict=True):
        assert marker in step


def test_the_pr_repository_flow_is_compose_review_then_pr(lane_text: str) -> None:
    assert "`compose`, `/code-review`, then `/pr`" in lane_text
    assert "--local-trunk" in section(
        lane_text, r"^### 4\. ", boundary_pattern=r"^### 5\. "
    )


@pytest.mark.parametrize(
    "fact",
    [
        "Removes the lane worktree",
        "Deletes the lane branch",
        "`continue-in:`",
        "`recover:`",
        "pushed: nothing; run git push yourself if wanted",
        "git branch <lane> <former-head>",
    ],
)
def test_integrate_states_what_it_removes_and_prints(lane_text: str, fact: str) -> None:
    assert fact in step_3(lane_text)


@pytest.mark.parametrize("line", ["`done:`", "`remaining:`", "`recover:`"])
def test_partial_failure_names_its_lines(lane_text: str, line: str) -> None:
    partial = section(lane_text, r"^### 5\. ", boundary_pattern=r"^## ")
    assert line in partial
    assert "Re-running `integrate` is not the fix" in partial


@pytest.mark.parametrize("what", sorted(REFUSALS))
def test_refusal_table_has_a_row_for_every_what(
    refusal_table_whats: list[str], what: str
) -> None:
    assert what in refusal_table_whats


def test_refusal_table_has_no_row_the_tool_lacks(
    refusal_table_whats: list[str],
) -> None:
    assert sorted(refusal_table_whats) == sorted(REFUSALS)


def test_refusal_table_rows_have_a_cause_and_a_fix(lane_text: str) -> None:
    rows = [
        line
        for line in section(
            lane_text, r"^## Refusals$", boundary_pattern=r"^## "
        ).splitlines()
        if TABLE_ROW.match(line)
    ]
    assert rows
    for row in rows:
        cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
        assert len(cells) == 3
        assert all(cells)


# --- branch-workflow: lanes versus /pr (Step 4.2) ---------------------------

BRANCH_WORKFLOW = PLUGIN_ROOT / "skills" / "branch-workflow" / "SKILL.md"
LANES_HEADING = "## Lanes versus pull requests"
OPTION_1_ORIGINAL = (
    "Integrate feature branch into base, run tests on merged result, "
    "delete feature branch, then call"
)


@pytest.fixture(scope="module")
def branch_workflow_text() -> str:
    return BRANCH_WORKFLOW.read_text()


def lanes_section(text: str) -> str:
    return section(text, rf"^{re.escape(LANES_HEADING)}$", boundary_pattern=r"^## ")


def option_1(text: str) -> str:
    return section(text, r"^1\. \*\*Merge locally\*\*", boundary_pattern=r"^2\. ")


def test_branch_workflow_has_the_pinned_heading_once(
    branch_workflow_text: str,
) -> None:
    assert branch_workflow_text.count(f"\n{LANES_HEADING}\n") == 1


@pytest.mark.parametrize(
    "phrase", ["without PRs", "/pr", "lane integrate", "--local-trunk"]
)
def test_lanes_section_has_the_pinned_phrase(
    branch_workflow_text: str, phrase: str
) -> None:
    assert phrase in lanes_section(branch_workflow_text)


def test_lanes_section_ends_at_the_next_heading(branch_workflow_text: str) -> None:
    assert "## Integration" not in lanes_section(branch_workflow_text)
    assert lanes_section(branch_workflow_text).strip()


def test_option_1_keeps_its_original_sentence_verbatim(
    branch_workflow_text: str,
) -> None:
    assert OPTION_1_ORIGINAL in option_1(branch_workflow_text)


def test_option_1_points_to_lane_integrate(branch_workflow_text: str) -> None:
    line = next(
        line
        for line in branch_workflow_text.splitlines()
        if line.startswith("1. **Merge locally**")
    )
    assert "`lane integrate`" in line
    assert "(#lanes-versus-pull-requests)" in line


def test_the_lanes_link_resolves_to_the_lane_skill(branch_workflow_text: str) -> None:
    assert "(../lane/SKILL.md)" in lanes_section(branch_workflow_text)
    assert (BRANCH_WORKFLOW.parent / "../lane/SKILL.md").resolve() == LANE_SKILL
