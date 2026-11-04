"""Content pins for skills/lane/SKILL.md (issue #2274, Slice 4).

The lane skill is prose over a real tool, so the pins that matter are the ones
that tie the prose to the tool: the refusal table is checked against
`lane_core.REFUSALS`, the Arguments table and the examples against the real
argparse parser, and the output labels and exit codes against the tool's own
constants. Wording pins cover the flow and the facts a reader acts on.
"""

from __future__ import annotations

import argparse
import re
import shlex
import sys

import pytest
from skill_doc_helpers import PLUGIN_ROOT, frontmatter, section

SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import lane
import lane_core
from lane_core import REFUSALS

LANE_SKILL = PLUGIN_ROOT / "skills" / "lane" / "SKILL.md"
LANE_COMMAND = '"${CLAUDE_PLUGIN_ROOT}/scripts/lane.py"'
TABLE_ROW = re.compile(r"^\|\s*`(?P<what>[^`]+)`\s*\|")
FLAG = re.compile(r"--[a-z][a-z-]*")
HEX_40 = "a" * 40
REGISTRY = PLUGIN_ROOT / "knowledge" / "agent-registry.md"
SKILLS_CATALOG = PLUGIN_ROOT / "docs" / "skills.md"

#: The exact tool grant. `git *` would pre-approve `git push`, which the skill
#: forbids, so each git subcommand the flow runs is granted on its own.
EXPECTED_GRANT = [
    "Read",
    f"Bash(python3 {LANE_COMMAND} *)",
    "Bash(git fetch *)",
    "Bash(git status *)",
    "Bash(git log *)",
]


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


def step(text: str, number: int) -> str:
    return section(text, rf"^### {number}\. ", boundary_pattern=r"^(### |## )")


def constraints(text: str) -> str:
    return section(text, r"^## Constraints$", boundary_pattern=r"^## ")


def command_flags(name: str) -> set[str]:
    """The `--flags` of one command, read from its own parser's usage line.

    `format_help()` is argparse's public rendering; the usage block ends at the
    first blank line, before any help text that could mention another flag.
    """
    parser = argparse.ArgumentParser(prog=f"lane.py {name}")
    lane.COMMANDS[name].configure(parser)
    usage = parser.format_help().split("\n\n")[0]
    return set(FLAG.findall(usage)) - {"--help"}


def arguments_rows(text: str) -> dict[str, str]:
    """`{command: arguments cell}` from the Arguments table."""
    arguments = section(text, r"^## Arguments$", boundary_pattern=r"^## Steps$")
    return {
        match["what"]: line
        for line in arguments.splitlines()
        if (match := TABLE_ROW.match(line))
    }


# --- frontmatter --------------------------------------------------------------


def test_frontmatter_names_a_user_invocable_worker(lane_text: str) -> None:
    head = frontmatter(lane_text)
    assert re.search(r"^name: lane$", head, re.MULTILINE)
    assert re.search(r"^role: worker$", head, re.MULTILINE)
    assert re.search(r"^user-invocable: true$", head, re.MULTILINE)


def test_allowed_tools_is_the_exact_grant(lane_text: str) -> None:
    grant = re.search(r"^allowed-tools: (.*)$", frontmatter(lane_text), re.MULTILINE)
    assert grant is not None
    assert re.split(r",\s*(?![^(]*\))", grant[1]) == EXPECTED_GRANT


@pytest.mark.parametrize(
    "forbidden", ["Bash(*)", "Bash(git *)", "git push", "Write", "Edit", "Bash,"]
)
def test_allowed_tools_grants_no_broad_or_writing_tool(
    lane_text: str, forbidden: str
) -> None:
    grant = re.search(r"^allowed-tools: (.*)$", frontmatter(lane_text), re.MULTILINE)
    assert grant is not None
    assert forbidden not in f"{grant[1]},"


def test_argument_hint_names_every_command_and_flag_of_the_tool(
    lane_text: str,
) -> None:
    hint = re.search(r'^argument-hint: "(.*)"$', frontmatter(lane_text), re.MULTILINE)
    assert hint is not None
    assert set(FLAG.findall(hint[1])) == set().union(
        *(command_flags(name) for name in lane.COMMANDS)
    )
    assert all(name in hint[1] for name in lane.COMMANDS)


def test_description_has_no_colon(lane_text: str) -> None:
    description = re.search(
        r"^description: (.*)$", frontmatter(lane_text), re.MULTILINE
    )
    assert description is not None
    assert ":" not in description[1]


def test_body_declares_the_worker_role_after_the_h1(lane_text: str) -> None:
    assert re.search(r"^# Lane\n\nRole: worker\.", lane_text, re.MULTILINE)


# --- commands, flags and examples ---------------------------------------------


def test_the_skill_documents_exactly_the_tools_commands(lane_text: str) -> None:
    shown = set(re.findall(rf"python3 {re.escape(LANE_COMMAND)} (\w+)", lane_text))
    assert shown == set(lane.COMMANDS)


def test_arguments_table_has_a_row_per_command(lane_text: str) -> None:
    assert set(arguments_rows(lane_text)) == set(lane.COMMANDS)


@pytest.mark.parametrize("name", sorted(lane.COMMANDS))
def test_arguments_row_flags_equal_the_commands_own_flags(
    lane_text: str, name: str
) -> None:
    assert set(FLAG.findall(arguments_rows(lane_text)[name])) == command_flags(name)


def example_argv(text: str, name: str) -> list[str]:
    """The argv of the first fenced `lane.py <name>` example, placeholders filled."""
    joined = re.sub(r"\\\n\s*", " ", text)
    line = next(
        line.strip()
        for line in joined.splitlines()
        if line.strip().startswith(f"python3 {LANE_COMMAND} {name}")
    )
    for placeholder, value in (
        ("<name>", "work"),
        ("<expected-trunk>", HEX_40),
        ("<expected-tree>", HEX_40),
    ):
        line = line.replace(placeholder, value)
    return shlex.split(line)[2:]


@pytest.mark.parametrize("name", sorted(lane.COMMANDS))
def test_each_example_is_accepted_by_the_real_parser(lane_text: str, name: str) -> None:
    args = lane.build_parser().parse_args(example_argv(lane_text, name))
    assert args.command == name


def test_the_integrate_example_carries_both_identities(lane_text: str) -> None:
    args = lane.build_parser().parse_args(example_argv(lane_text, "integrate"))
    assert (args.expected_trunk, args.expected_tree) == (HEX_40, HEX_40)


def test_exit_codes_are_the_tools(lane_text: str) -> None:
    ok, refused, usage = (
        lane_core.EXIT_OK,
        lane_core.EXIT_REFUSED,
        lane_core.EXIT_USAGE,
    )
    assert f"Exit codes: {ok} success, {refused} refusal, {usage} usage error." in (
        lane_text
    )


# --- flow ---------------------------------------------------------------------


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
    for line, marker in zip(steps, markers, strict=True):
        assert marker in line


def test_open_names_the_default_path_and_prints_its_labels(lane_text: str) -> None:
    opened = step(lane_text, 1)
    assert (
        f"`<checkout>{lane.LANE_DIR_INFIX}<name>`, with `/` in the name replaced"
        in (opened)
    )
    assert "It prints `worktree:` and `branch:`." in opened


def test_compose_prints_five_lines_and_the_expected_two_are_the_flags(
    lane_text: str,
) -> None:
    expected = [
        flag.removeprefix("--")
        for flag in (lane.EXPECTED_TRUNK_FLAG, lane.EXPECTED_TREE_FLAG)
    ]
    labels = ["lane", lane.KEY_TRUNK, *expected, "next"]
    composed = step(lane_text, 2)
    assert "It prints five lines: " in composed
    for label in labels:
        assert f"`{label}:`" in composed


def test_compose_restores_the_lane_and_prints_no_identities_on_a_conflict(
    lane_text: str,
) -> None:
    assert (
        "On a conflict or a rejected merge it restores the lane to the state it had "
        "before and prints no identities."
    ) in step(lane_text, 2)


def test_compose_merges_the_local_trunk_branch_when_it_has_commits_the_ref_lacks(
    lane_text: str,
) -> None:
    assert "(and the local trunk branch, when it has commits the trunk ref lacks)" in (
        step(lane_text, 2)
    )


def test_integrate_example_is_run_with_compose_s_values_and_trunk(
    lane_text: str,
) -> None:
    integrate = step(lane_text, 3)
    assert "Run it, or pass the same values to the command above" in integrate
    assert "with the same `--trunk` that you gave to `compose`." in integrate


def test_integrate_runs_all_the_checks_and_reports_each_failing_one(
    lane_text: str,
) -> None:
    assert len(lane.CHECKS) == 6
    assert "`integrate` runs all six checks and reports each failing one." in step(
        lane_text, 3
    )


@pytest.mark.parametrize(
    "fact",
    [
        "Removes the lane worktree",
        "Deletes the lane branch",
        "git branch <lane> <former-head>",
        f"`{lane.PUSHED_NOTHING_LINE}`",
        *(
            f"`{key}:`"
            for key in (
                lane.KEY_TRUNK,
                lane.KEY_FORMER_HEAD,
                lane.KEY_NOW_AT,
                lane.KEY_CONTINUE_IN,
                lane.KEY_RECOVER,
            )
        ),
    ],
)
def test_integrate_states_what_it_removes_and_prints(lane_text: str, fact: str) -> None:
    assert fact in step(lane_text, 3)


def test_the_pr_repository_flow_is_compose_review_then_pr(lane_text: str) -> None:
    assert "`compose`, `/code-review`, then `/pr`" in step(lane_text, 4)


def test_compose_prints_the_pr_next_line_in_a_pr_repository(lane_text: str) -> None:
    assert f"`next: {lane.PR_NEXT_STEP}`" in step(lane_text, 4)


def test_integrate_refuses_a_pr_repository(lane_text: str) -> None:
    assert "`integrate` refuses with `PR repository`." in step(lane_text, 4)
    assert lane_core.WHAT_PR_REPOSITORY == "PR repository"


@pytest.mark.parametrize(
    "claim",
    [
        "To land locally anyway, pass `--local-trunk` to `integrate`.",
        "`open` ignores the origin.",
        (
            "`compose` reads it only to choose its `next:` line and never refuses "
            "because of a GitHub origin (`compose` has no `--local-trunk`)."
        ),
    ],
)
def test_origin_handling_is_stated_per_command(lane_text: str, claim: str) -> None:
    assert claim in step(lane_text, 4)
    assert "--local-trunk" not in command_flags("compose")
    assert "--local-trunk" in command_flags("integrate")


@pytest.mark.parametrize(
    "bullet",
    [
        (
            "- Do not push. `integrate` never pushes; it changes local refs and removes "
            "the lane worktree (deleting every ignored file in it). The human runs "
            "`git push` if wanted."
        ),
        "- Do not bypass git hooks, force anything, or edit the refusal text.",
        "- Do not retry a failed command in a loop.",
        (
            "- Do not run `integrate` in a repository whose `origin` is on GitHub unless "
            "the human asks for `--local-trunk`. Use `/pr` instead."
        ),
    ],
)
def test_constraints_state_the_prohibition(lane_text: str, bullet: str) -> None:
    assert bullet in constraints(lane_text)


# --- partial failure ----------------------------------------------------------


@pytest.mark.parametrize(
    "line", [lane.LINE_DONE, lane.LINE_REMAINING, lane.KEY_RECOVER]
)
def test_partial_failure_names_its_lines(lane_text: str, line: str) -> None:
    assert f"- `{line}:`" in step(lane_text, 5)


def test_partial_failure_says_rerunning_integrate_is_not_the_fix(
    lane_text: str,
) -> None:
    assert "Re-running `integrate` is not the fix." in step(lane_text, 5)


def test_partial_failure_says_what_to_do_when_the_step_cannot_be_repeated(
    lane_text: str,
) -> None:
    partial = step(lane_text, 5)
    assert (
        f"When the step cannot be repeated by hand, no `{lane.LINE_REMAINING}:` "
        "lines are printed and `how:` says what to check instead."
    ) in partial
    assert (
        "Follow `how:`, and inspect the trunk branch with git before any other action."
    ) in partial


# --- refusals -----------------------------------------------------------------


def test_refusal_table_whats_equal_the_tools_refusals(
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


@pytest.mark.parametrize(
    ("what", "claim"),
    [
        (
            lane_core.WHAT_TREE_MISMATCH,
            (
                "For the tree, `why:` shows `expected:` and `live:`. When the lane HEAD "
                "moved, it shows `checked:` and `live:`."
            ),
        ),
        (
            lane_core.WHAT_TRUNK_CANNOT_FAST_FORWARD,
            (
                "When the branch is not an ancestor, run `compose`, then "
                "`/code-review --since <trunk>` in the lane, and pass the new identities."
            ),
        ),
        (
            lane_core.WHAT_LANE_HAS_UNCOMMITTED_CHANGES,
            "conclude it with `git commit` or abort it with `git merge --abort`.",
        ),
        (
            lane_core.WHAT_INTEGRATE_STEP_FAILED,
            (
                "If none are printed, follow `how:` and inspect the trunk branch with git "
                "first. Do not re-run `integrate`."
            ),
        ),
    ],
)
def test_refusal_row_states_the_fix_the_tool_prints(
    lane_text: str, what: str, claim: str
) -> None:
    row = next(
        line
        for line in lane_text.splitlines()
        if (match := TABLE_ROW.match(line)) and match["what"] == what
    )
    assert claim in row


# --- registration -------------------------------------------------------------


def test_the_skill_is_registered_in_the_agent_registry() -> None:
    row = next(
        line
        for line in REGISTRY.read_text().splitlines()
        if line.startswith("| Lane |")
    )
    assert "`skills/lane/SKILL.md`" in row
    assert "Software Engineer" not in row


def test_the_skill_is_listed_in_the_catalog_with_its_options() -> None:
    row = next(
        line
        for line in SKILLS_CATALOG.read_text().splitlines()
        if line.startswith("| `/lane` |")
    )
    options = row.split(" | ")[1]
    assert options.strip() not in ("", "no flags — run directly")
    assert "lane/SKILL.md" in row


# --- branch-workflow: lanes versus /pr (Step 4.2) ------------------------------

BRANCH_WORKFLOW = PLUGIN_ROOT / "skills" / "branch-workflow" / "SKILL.md"
LANES_HEADING = "## Lanes versus pull requests"
#: Option 1 as it read before the lanes pointer was appended (`aa62e1f`).
OPTION_1_ORIGINAL = (
    "1. **Merge locally** — Integrate feature branch into base, run tests on "
    'merged result, delete feature branch, then call `ExitWorktree(action="remove")`'
)
#: Options 2 to 4, unchanged since `aa62e1f`.
OPTIONS_2_TO_4_ORIGINAL = [
    (
        "2. **Push and create PR** — Push branch and create pull request via "
        '`gh pr create`. Once the PR is opened, call `ExitWorktree(action="keep")` so '
        "the worktree persists on disk while the session's CWD bookkeeping is closed"
    ),
    (
        "3. **Keep as-is** — Preserve branch and worktree for later handling; call "
        '`ExitWorktree(action="keep")` immediately after the option is confirmed — do '
        'not leave the worktree silently "entered" for the rest of the session'
    ),
    (
        "4. **Discard** — Permanently delete branch and all commits. **Requires the "
        'human to type "discard" to confirm.** Never discard without typed confirmation. '
        'After confirmation, call `ExitWorktree(action="remove", discard_changes=true)`'
    ),
]


@pytest.fixture(scope="module")
def branch_workflow_text() -> str:
    return BRANCH_WORKFLOW.read_text()


def lanes_section(text: str) -> str:
    return section(text, rf"^{re.escape(LANES_HEADING)}$", boundary_pattern=r"^## ")


def heading_anchor(heading: str) -> str:
    """GitHub's anchor for a heading: lowercase, punctuation dropped, spaces to `-`."""
    words = re.sub(r"[^a-z0-9 -]", "", heading.removeprefix("## ").lower())
    return words.replace(" ", "-")


def test_branch_workflow_has_the_pinned_heading_once(
    branch_workflow_text: str,
) -> None:
    assert branch_workflow_text.count(f"\n{LANES_HEADING}\n") == 1


@pytest.mark.parametrize(
    "claim",
    [
        "Use a lane for repositories without PRs.",
        (
            "`lane integrate` fast-forwards local trunk only when the reviewed tree, "
            "the review gate, and the trunk commit still match."
        ),
        "It removes the lane worktree and branch, and it never pushes.",
        "Use `/pr` for GitHub repositories.",
        "`lane integrate` refuses when `origin` is on GitHub.",
        "To integrate locally anyway, pass `--local-trunk`.",
    ],
)
def test_lanes_section_states_the_claim(branch_workflow_text: str, claim: str) -> None:
    assert claim in lanes_section(branch_workflow_text)


def options_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if re.match(r"[1-4]\. \*\*", line)]


def test_option_1_keeps_its_original_sentence_verbatim(
    branch_workflow_text: str,
) -> None:
    (line,) = [
        line for line in options_lines(branch_workflow_text) if line.startswith("1. ")
    ]
    assert line.startswith(OPTION_1_ORIGINAL)


def test_options_2_to_4_are_unchanged(branch_workflow_text: str) -> None:
    assert options_lines(branch_workflow_text)[1:] == OPTIONS_2_TO_4_ORIGINAL


def test_option_1_points_to_lane_integrate_at_the_lanes_section(
    branch_workflow_text: str,
) -> None:
    line = next(
        line for line in options_lines(branch_workflow_text) if line.startswith("1. ")
    )
    assert "`lane integrate`" in line
    assert f"(#{heading_anchor(LANES_HEADING)})" in line


def test_the_lanes_link_resolves_to_the_lane_skill(branch_workflow_text: str) -> None:
    link = re.search(r"\[`/lane`\]\(([^)]+)\)", lanes_section(branch_workflow_text))
    assert link is not None
    assert (BRANCH_WORKFLOW.parent / link[1]).resolve() == LANE_SKILL
