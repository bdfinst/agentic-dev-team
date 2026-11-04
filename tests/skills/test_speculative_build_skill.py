"""Doc-shape contract for speculative-build/SKILL.md (plan Slice 3).

The skill is a procedure `/build --candidates N` follows for one `complex`
step. These tests pin the contract the plan's Slice 3 Gherkin names: the
frontmatter, the twelve sections in order, the phrases each section must carry,
and the halt template of `## Failure modes`. Script resolution is checked
mechanically: every `python3 "${CLAUDE_PLUGIN_ROOT}/..."` call in a fenced
block must name a script that exists, and every flag named for an argparse
script must appear in that subcommand's real `--help`. Registration is checked
last: the registry row and the `docs/skills.md` row. The exit codes of
`check_registry_sync.py` and `build_skills_index.py --check` are already gated
by `tests/repo/test_registry_sync.py` and `tests/repo/test_skills_index_current.py`.
"""

from __future__ import annotations

import functools
import os
import re
import subprocess
import sys
from collections.abc import Callable

import pytest
from skill_doc_helpers import (
    PLUGIN_ROOT,
    Fact,
    assert_fact,
    collapsed,
    frontmatter,
    grep,
    headings_outside_code,
    section,
    section_outside_code,
)

SKILL = PLUGIN_ROOT / "skills" / "speculative-build" / "SKILL.md"
REGISTRY = PLUGIN_ROOT / "knowledge" / "agent-registry.md"
SKILLS_DOC = PLUGIN_ROOT / "docs" / "skills.md"

SECTION_ORDER = [
    "Preconditions",
    "Base and batches",
    "Dispatch",
    "Suite and diff",
    "Screening",
    "Cost cap",
    "Rank",
    "Record",
    "Keep",
    "Cleanup",
    "Resume",
    "Failure modes",
]

#: Placeholders that name a branch or a worktree path. Each must be
#: single-quoted wherever it appears in a bash block.
QUOTED_PLACEHOLDERS = (
    "<branch>",
    "<branch-1>",
    "<branch-2>",
    "<winner-branch>",
    "<build-branch>",
    "<worktree>",
    "<build-worktree>",
    "<plan>",
)


#: A shipped-script call in the skill: the script path under the plugin root,
#: then the rest of the line (subcommand and flags).
_INVOCATION_RE = re.compile(r'python3 "\$\{CLAUDE_PLUGIN_ROOT\}/([^"]+)"(.*)$')
#: Argparse scripts whose subcommands and flags are checked against their real
#: `--help`. `build_jobs.py` prints a hand-written usage line on stderr with
#: exit 2, and `build_worktree_baseref.py` has no `--help`, so both get the
#: existence check only.
HELP_CHECKED_SCRIPTS = (
    "scripts/build_candidates.py",
    "scripts/plan_summary_record.py",
    "scripts/build_slice_scope.py",
    "hooks/lib/cost_meter.py",
)
HELP_TIMEOUT_SECONDS = 60
HALT_TEMPLATE_LINE_COUNT = 7
BUILD_CANDIDATES_SUBCOMMANDS = {
    "validate-flags",
    "collect",
    "rank",
    "project",
    "reconcile",
    "cleanup",
}


def _fenced_command_lines(text: str) -> list[str]:
    """Lines of every ```bash and ```text fenced block."""
    blocks = re.findall(
        r"^```(?:bash|text)\n(.*?)^```", text, flags=re.DOTALL | re.MULTILINE
    )
    return [line for block in blocks for line in block.splitlines()]


def _invocations(text: str) -> list[tuple[str, str, tuple[str, ...]]]:
    """`(script path under the plugin root, subcommand, long flags)` for each
    `python3 "${CLAUDE_PLUGIN_ROOT}/..."` call in a fenced bash or text block."""
    found = []
    for line in _fenced_command_lines(text):
        match = _INVOCATION_RE.search(line)
        if not match:
            continue
        script, rest = match.groups()
        words = rest.split()
        first = words[0] if words else ""
        subcommand = "" if first.startswith(("-", "<")) else first
        flags = tuple(re.findall(r"(?<![\w-])(--[a-z][a-z-]*)", rest))
        found.append((script, subcommand, flags))
    return found


INVOCATIONS = _invocations(SKILL.read_text(encoding="utf-8"))


@functools.cache
def _help_text(script: str, subcommand: str) -> str:
    # Python 3.14 argparse colours its help output; plain text is what we match.
    env = {k: v for k, v in os.environ.items() if k != "FORCE_COLOR"}
    env["NO_COLOR"] = "1"
    command = [sys.executable, str(PLUGIN_ROOT / script)]
    command += [subcommand] if subcommand else []
    result = subprocess.run(
        [*command, "--help"],
        capture_output=True,
        text=True,
        timeout=HELP_TIMEOUT_SECONDS,
        check=False,
        env=env,
    )
    assert result.returncode == 0, f"{script} {subcommand} --help: {result.stderr}"
    return result.stdout


@pytest.fixture(scope="module")
def skill_text() -> str:
    return SKILL.read_text(encoding="utf-8")


def _h2(name: str) -> Callable[[str], str]:
    """Resolve a `## <name>` section of the skill, up to the next `## ` outside
    a fenced block."""
    return lambda text: section_outside_code(
        text, rf"^## {name}$", boundary_pattern=r"^## "
    )


SECTIONS: dict[str, Callable[[str], str]] = {
    "frontmatter": frontmatter,
    **{name: _h2(name) for name in SECTION_ORDER},
}


def _bash_blocks(text: str) -> list[str]:
    return re.findall(r"^```bash\n(.*?)^```", text, flags=re.DOTALL | re.MULTILINE)


def test_skill_frontmatter_declares_name_and_orchestrator_role(skill_text):
    fm = frontmatter(skill_text)
    assert grep(r"^name: speculative-build$", fm)
    assert grep(r"^role: orchestrator$", fm)


def test_skill_frontmatter_grants_bare_bash(skill_text):
    assert grep(r"^allowed-tools: Bash$", frontmatter(skill_text))


def test_skill_frontmatter_has_no_user_invocable_or_argument_hint(skill_text):
    fm = frontmatter(skill_text)
    assert not grep(r"^user-invocable:", fm)
    assert not grep(r"^argument-hint:", fm)


def test_skill_description_names_build_candidates_as_only_entry_point(skill_text):
    description = collapsed(
        section(
            frontmatter(skill_text),
            r"^description:",
            boundary_pattern=r"^[a-z-]+:",
            include_start_line=False,
        )
    )
    assert "Reached only through /build --candidates N" in description
    assert "Not user-invocable" in description


def test_skill_body_has_the_twelve_sections_in_order(skill_text):
    assert headings_outside_code(skill_text, 2) == SECTION_ORDER


def test_failure_modes_halt_template_is_a_fenced_text_block(skill_text):
    body = section(skill_text, r"^## Failure modes$", boundary_pattern=r"^## ")
    blocks = re.findall(r"^```text\n(.*?)^```", body, flags=re.DOTALL | re.MULTILINE)
    assert len(blocks) == 1
    assert blocks[0].startswith("speculative dispatch halted at step <step>")
    lines = blocks[0].splitlines()
    assert len(lines) == HALT_TEMPLATE_LINE_COUNT, (
        f"halt template has {len(lines)} lines, expected {HALT_TEMPLATE_LINE_COUNT}"
    )


def test_skill_body_opens_with_one_h1_before_the_sections(skill_text):
    assert headings_outside_code(skill_text, 1) == ["Speculative build"]
    assert skill_text.index("\n# Speculative build\n") < skill_text.index(
        "\n## Preconditions\n"
    )


def test_skill_names_no_model(skill_text):
    assert not grep(r"opus|sonnet|haiku|fable", skill_text, ignore_case=True)


def test_skill_names_no_tracker_number(skill_text):
    assert not grep(r"#[0-9]{3,}", skill_text)


def test_skill_names_the_plan_step_as_step_not_n_dot_m(skill_text):
    assert "<N.M>" not in skill_text


@pytest.mark.parametrize("placeholder", QUOTED_PLACEHOLDERS)
def test_skill_bash_blocks_single_quote_branch_and_worktree_placeholders(
    skill_text, placeholder
):
    bash_lines = [
        line for block in _bash_blocks(skill_text) for line in block.splitlines()
    ]
    quoted = f"'{placeholder}'"
    assert any(quoted in line for line in bash_lines), f"{placeholder} never appears"
    command_lines = [
        line
        for line in _fenced_command_lines(skill_text)
        if _INVOCATION_RE.search(line)
    ]
    bare = re.compile(rf"(?<!'){re.escape(placeholder)}|{re.escape(placeholder)}(?!')")
    offenders = [line for line in command_lines if bare.search(line)]
    assert not offenders, f"{placeholder} is not single-quoted in: {offenders}"


@pytest.mark.parametrize(
    ("text", "level", "expected"),
    [
        ("# a\n```\n## fake\n```\n## y\n", 2, ["y"]),
        ("# a\n```\n# fake\n```\n## y\n", 1, ["a"]),
        ("```text\n## fake\n```\n", 2, []),
    ],
    ids=["fenced_h2_ignored", "fenced_h1_ignored", "only_fenced"],
)
def test_headings_outside_code_skips_fenced_lines(text, level, expected):
    assert headings_outside_code(text, level) == expected


def test_section_stays_open_across_a_fenced_h2_line():
    text = "## A\nbody\n```\n## fake\ninside\n```\ntail\n## B\nother\n"
    body = _h2("A")(text)
    assert "inside" in body
    assert "tail" in body
    assert "other" not in body


def _invocation_id(invocation: tuple[str, str, tuple[str, ...]]) -> str:
    script, subcommand, flags = invocation
    return f"{script.rsplit('/', 1)[-1]}-{subcommand or 'nosub'}-{'-'.join(flags)}"


@pytest.mark.parametrize("invocation", INVOCATIONS, ids=_invocation_id)
def test_every_script_the_skill_invokes_exists_under_the_plugin_root(invocation):
    assert (PLUGIN_ROOT / invocation[0]).is_file()


@pytest.mark.parametrize(
    "invocation",
    [i for i in INVOCATIONS if i[0] in HELP_CHECKED_SCRIPTS],
    ids=_invocation_id,
)
def test_every_flag_the_skill_names_is_listed_by_the_subcommand_help(invocation):
    script, subcommand, flags = invocation
    assert subcommand, f"{script} is called without a subcommand"
    help_text = _help_text(script, subcommand)
    missing = [
        flag
        for flag in flags
        if not re.search(rf"(?<![\w-]){re.escape(flag)}(?![\w-])", help_text)
    ]
    assert not missing, f"{script} {subcommand} --help does not list {missing}"


def test_skill_invokes_every_build_candidates_subcommand_and_record():
    seen = {(script, sub) for script, sub, _ in INVOCATIONS}
    expected = {
        ("scripts/build_candidates.py", sub) for sub in BUILD_CANDIDATES_SUBCOMMANDS
    }
    expected.add(("scripts/plan_summary_record.py", "record"))
    assert expected <= seen


FACTS = [
    # Preconditions
    Fact(
        "preconditions_name_validate_flags_transcript_and_baseref_head",
        "Preconditions",
        literal_required=(
            "validate-flags",
            "session transcript",
            "worktree.baseRef",
            "`head`",
        ),
    ),
    Fact(
        "preconditions_require_the_agent_or_task_tool_and_halt_before_batch_1",
        "Preconditions",
        literal_required=(
            "`/build` holds the `Agent` (or `Task`) tool.",
            "If the `Agent` (or `Task`) tool is missing, halt before batch 1.",
            "`/build`'s Orchestrator constraints prescribe",
        ),
    ),
    Fact(
        "preconditions_halt_when_invoked_outside_build",
        "Preconditions",
        literal_required=(
            (
                "`speculative dispatch requires a session transcript, "
                "worktree.baseRef = head and validated flags; "
                "run /build, not this skill`"
            ),
            "This skill halts when you invoke it outside `/build`.",
        ),
    ),
    # Base and batches
    Fact(
        "preconditions_halt_writes_no_record_and_prints_only_its_own_message",
        "Preconditions",
        literal_required=(
            "A Preconditions halt writes no record and prints only its own message.",
        ),
    ),
    Fact(
        "base_and_batches_open_with_the_six_step_batch_loop",
        "Base and batches",
        literal_required=(
            "1. Read `prev` from the cost meter.",
            (
                "2. Hash the plan file, dispatch the batch, then hash it again. "
                "Halt if the hashes differ."
            ),
            "3. Read `now`. Compute `delta = now - prev`. Add `delta` to `spent`.",
            "4. Run the suite in each candidate worktree.",
            "5. Screen each candidate, then run `collect`.",
            "6. Run `project`, then dispatch the next batch. After the last batch, go to Rank.",
        ),
    ),
    Fact(
        "base_and_batches_attempt_is_one_plus_the_highest_recorded_attempt",
        "Base and batches",
        literal_required=(
            (
                "Set attempt `k` to 1 plus the highest attempt number "
                "the plan's table records for the step. Use 0 when it records none."
            ),
        ),
    ),
    Fact(
        "base_and_batches_echo_the_step_line_once_k_is_derived",
        "Base and batches",
        literal_required=(
            (
                "Print `speculative dispatch: step <step>, <N> candidates, "
                "cost cap $<X>, attempt <k>`."
            ),
        ),
    ),
    Fact(
        "base_and_batches_define_the_recurring_placeholders",
        "Base and batches",
        literal_required=(
            "- `<X>` is the cap from `--max-cost-usd`.",
            "- `<P>` is the projected total that `project` prints.",
            "- `<b>` is the batch number.",
            "- `<ks>` lists the earlier attempt numbers.",
        ),
    ),
    Fact(
        "base_and_batches_stale_branches_take_disk_space_only",
        "Base and batches",
        literal_required=(
            "Stale branches take disk space only.",
            "Dispatch never creates a branch with one of these names.",
        ),
    ),
    Fact(
        "base_and_batches_batch_1_is_candidate_1_alone",
        "Base and batches",
        literal_required=("Make batch 1 candidate 1 alone",),
    ),
    Fact(
        "base_and_batches_later_batches_are_sized_by_the_build_jobs_wave",
        "Base and batches",
        literal_required=(
            "`build_jobs.py`'s wave is this skill's batch.",
            "--wave-width <N-1>",
            "Do not pass `--jobs`.",
        ),
    ),
    # Dispatch
    Fact(
        "dispatch_states_agent_isolation_frontmatter_and_prompt",
        "Dispatch",
        literal_required=(
            "software-engineer",
            'isolation: "worktree"',
            "declared frontmatter",
            "Candidate <i> of <N>",
            "commit every green on your worktree branch",
            "For each step within a slice, dispatch",
        ),
    ),
    Fact(
        "dispatch_prompt_forbids_writing_the_plan_file",
        "Dispatch",
        literal_required=("Do not write the plan file",),
    ),
    Fact(
        "dispatch_prompt_carries_the_freeze_engage_line_when_freeze_would_engage",
        "Dispatch",
        literal_required=(
            (
                "Before your first edit run: "
                'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build_slice_scope.py" '
                "engage '<plan>' --slice <slice-id> "
                "--hooks-dir '<your worktree>/.claude/hooks'"
            ),
            (
                "Add the third line only when `/build`'s Slice dispatch bookkeeping "
                "step 1 would engage freeze."
            ),
            "this check exits 0 and the slice declares `**Files:**`",
        ),
    ),
    Fact(
        "dispatch_each_candidate_commits_on_its_own_branch",
        "Dispatch",
        literal_required=("Each candidate commits on its own worktree branch.",),
    ),
    Fact(
        "dispatch_each_candidate_writes_its_own_build_phase_json",
        "Dispatch",
        literal_required=(
            "its own `.claude/memory/build-phase.json`",
            "standalone-dispatch fallback",
        ),
    ),
    Fact(
        "dispatch_freeze_state_leaves_with_the_candidate_worktree",
        "Dispatch",
        literal_required=(
            "The freeze state, when engaged, leaves with the candidate's worktree.",
        ),
    ),
    Fact(
        "dispatch_only_the_parent_writes_the_plan_file",
        "Dispatch",
        literal_required=("Only the parent writes the plan file.",),
    ),
    Fact(
        "dispatch_rollback_point_is_the_one_build_recorded_and_the_skill_records_none",
        "Dispatch",
        literal_required=(
            (
                "The step's rollback point is the one `/build` recorded "
                "before the slice's first step, if the slice declares one."
            ),
            "This skill records none.",
        ),
    ),
    Fact(
        "dispatch_pairs_each_result_with_its_dispatch_id",
        "Dispatch",
        literal_required=(
            "Pair each returned result with the dispatch that produced it.",
            "Candidate `<i>` is that dispatch's id.",
        ),
    ),
    Fact(
        "dispatch_branch_is_read_from_the_result_and_confirmed_with_worktree_list",
        "Dispatch",
        literal_required=(
            "Read the `branch:` line of the dispatch result.",
            "git worktree list --porcelain",
        ),
    ),
    Fact(
        "dispatch_accepts_a_branch_only_when_listed_and_matching_the_name_regex",
        "Dispatch",
        literal_required=(
            "exactly matches a `branch refs/heads/<name>` entry",
            "`^[A-Za-z0-9._/][A-Za-z0-9._/-]*$`",
        ),
    ),
    Fact(
        "dispatch_takes_the_worktree_path_from_the_porcelain_entry_only",
        "Dispatch",
        literal_required=(
            (
                "Take `<worktree>` from the `worktree <path>` line "
                "of that same porcelain entry."
            ),
            "Never take it from the dispatch result.",
        ),
    ),
    Fact(
        "dispatch_uses_an_empty_branch_when_the_name_was_rejected",
        "Dispatch",
        literal_required=("Use an empty branch when the name was rejected.",),
    ),
    Fact(
        "dispatch_hashes_the_plan_file_before_the_batch_and_stores_the_blob",
        "Dispatch",
        literal_required=(
            (
                "Hash the parent's plan file in the build worktree "
                "just before the batch dispatches."
            ),
            "The `-w` flag stores the blob:",
            "git hash-object -w '<plan>'",
        ),
    ),
    Fact(
        "dispatch_hashes_the_plan_file_again_when_the_batch_returns",
        "Dispatch",
        literal_required=("Hash it again when the batch returns:",),
    ),
    Fact(
        "dispatch_halts_when_the_plan_file_hash_changes",
        "Dispatch",
        literal_required=(
            "If the two hashes differ, a candidate wrote the parent's plan file.",
            (
                "Halt with the reason `plan file changed during batch <b> "
                "(changed file saved as <plan>.batch-<b>)`."
            ),
            "A non-zero exit from either hash is a script failure. Halt.",
        ),
    ),
    Fact(
        "dispatch_saves_the_changed_plan_and_restores_the_pre_batch_content",
        "Dispatch",
        literal_required=(
            "Before you write the halt record, do these steps:",
            "1. Copy the changed file aside.",
            "2. Restore the pre-batch content with `<pre-hash>`, the first hash.",
            "cp -- '<plan>' '<plan>'.batch-<b>",
            "git cat-file blob <pre-hash> > '<plan>'",
        ),
    ),
    Fact(
        "dispatch_takes_suite_from_the_restored_plan_and_omits_the_batch_from_merge",
        "Dispatch",
        literal_required=(
            "3. Take `<suite>` for the template from the restored plan.",
            "4. Leave that batch's candidates out of the merge-by-hand line.",
        ),
    ),
    Fact(
        "dispatch_counts_commits_beyond_base_to_find_a_no_commits_candidate",
        "Dispatch",
        literal_required=("git rev-list --count <base>..'<branch>'",),
    ),
    Fact(
        "dispatch_without_commits_is_a_candidate_with_suite_green_false",
        "Dispatch",
        literal_required=(
            "no-commits candidate",
            "`suite_green` false",
            "the reason `no commits`",
            "It is not a halt.",
            "It skips Suite and diff and Screening.",
        ),
    ),
    Fact(
        "dispatch_no_commits_dict_uses_the_cost_placeholder",
        "Dispatch",
        literal_required=(
            "`<cost>` to its cost",
            '"cost_usd": <cost>',
            '"branch": "<name or empty>"',
        ),
    ),
    # Suite and diff, Screening
    Fact(
        "suite_is_run_by_the_orchestrator_and_the_agent_report_is_advisory",
        "Suite and diff",
        literal_required=(
            "Run the plan's suite command in each candidate worktree yourself.",
            "The agent's own report is advisory.",
        ),
    ),
    Fact(
        "suite_command_and_plan_come_from_the_parent_build_worktree",
        "Suite and diff",
        literal_required=(
            (
                "The suite command and `--plan` always come "
                "from the parent's build worktree."
            ),
            "( cd '<worktree>' && <suite> ); echo \"suite-exit=$?\"",
        ),
    ),
    Fact(
        "screening_runs_the_spec_compliance_lens_with_json",
        "Screening",
        literal_required=(
            (
                "`/review-agent spec-compliance-review --internal --json "
                "--path '<worktree>' --since <base>`"
            ),
        ),
    ),
    Fact(
        "screening_runs_the_correctness_lens_with_json",
        "Screening",
        literal_required=(
            (
                "`/review-agent correctness-review --internal --json "
                "--path '<worktree>' --since <base>`"
            ),
        ),
    ),
    Fact(
        "screening_since_resolves_in_the_path_worktree_repository",
        "Screening",
        literal_required=(
            "`--since <base>` resolves in the repository of the `--path` worktree.",
            "`base` is an ancestor of the candidate branch.",
        ),
    ),
    Fact(
        "screening_collect_counts_unmet_findings_and_clamps_to_the_total",
        "Screening",
        literal_required=(
            "collect",
            "uncovered-scenario",
            "unmet-criterion",
            "It clamps the unmet count to `scenarios_total`.",
        ),
    ),
    Fact(
        "screening_records_a_plan_file_edit_and_does_not_rank_it",
        "Screening",
        literal_required=(
            "git diff --name-only --end-of-options <base>..'<branch>' -- '<plan>'",
            "Record it as `disqualified` with the reason `plan file edited`.",
            "Do not rank it.",
        ),
    ),
    Fact(
        "screening_plan_file_check_runs_in_the_parent_worktree_and_halts_on_failure",
        "Screening",
        literal_required=(
            (
                "Run this check in the parent's build worktree, "
                "with the repo-relative plan path."
            ),
            "A non-zero exit is a script failure. Halt.",
        ),
    ),
    Fact(
        "screening_plan_file_edited_candidate_keeps_its_dict_and_branch",
        "Screening",
        literal_required=("keep the candidate's `collect` dict and its branch.",),
    ),
    Fact(
        "screening_says_the_winner_is_screened_again_by_design",
        "Screening",
        literal_required=("The winner is therefore screened again by design.",),
    ),
    # Cost cap
    Fact(
        "cost_cap_names_the_meter_the_projection_and_the_flags",
        "Cost cap",
        literal_required=(
            'cost_meter.py" report --transcript',
            "--json",
            "totals.cost_usd",
            'build_candidates.py" project',
            "--last-batch-delta",
        ),
    ),
    Fact(
        "cost_cap_spent_starts_at_zero_before_batch_1",
        "Cost cap",
        literal_required=("Set `spent` to 0 before batch 1.",),
    ),
    Fact(
        "cost_cap_prev_is_read_before_every_batch_including_batch_1",
        "Cost cap",
        literal_required=(
            "Read `prev` just before every batch dispatches, including batch 1.",
        ),
    ),
    Fact(
        "cost_cap_reads_now_right_after_dispatch_before_suite_and_screening",
        "Cost cap",
        literal_required=(
            (
                "Read `now` immediately after the batch's dispatches return, "
                "before Suite and diff and before Screening."
            ),
        ),
    ),
    Fact(
        "cost_cap_delta_is_now_minus_prev_and_is_added_to_spent",
        "Cost cap",
        literal_required=(
            "Compute `delta = now - prev`.",
            "Add it to `spent`.",
            "`delta` and `spent` count candidate dispatch spend only.",
        ),
    ),
    Fact(
        "cost_cap_per_candidate_cost_is_the_batch_delta_over_the_dispatched_width",
        "Cost cap",
        literal_required=(
            "`cost_usd = delta / width`",
            "`width` is the number of candidates actually dispatched in that batch.",
        ),
    ),
    Fact(
        "cost_cap_projects_before_every_batch_after_the_first_never_inside_one",
        "Cost cap",
        literal_required=(
            "`project` runs before every batch after the first, while candidates remain.",
            "It never runs inside a batch.",
        ),
    ),
    Fact(
        "cost_cap_defines_the_project_placeholders",
        "Cost cap",
        literal_required=(
            "- `<S>` is `spent`.",
            (
                "- `<C>` is the number of candidates dispatched so far, "
                "including no-commits ones."
            ),
            "- `<R>` is N - C.",
            "- `<D>` is the last batch's `delta`.",
        ),
    ),
    Fact(
        "cost_cap_stop_records_undispatched_and_halt_is_a_failure_mode",
        "Cost cap",
        literal_required=(
            (
                "`stop`: record every undispatched candidate as `not dispatched` "
                "with the reason `cost cap`."
            ),
            "`halt`: treat it as a failure mode.",
        ),
    ),
    Fact(
        "cost_cap_names_both_status_line_forms",
        "Cost cap",
        literal_required=(
            (
                "`speculative <step>: batch <b> done — spent $<S> of $<X>, "
                "projected $<P>, <decision>`"
            ),
            (
                "`speculative <step>: batch <b> done — spent $<S> of $<X>, "
                "no candidates remain`"
            ),
        ),
    ),
    # Rank, Record, Keep, Cleanup, Resume
    Fact(
        "rank_excludes_plan_file_edited_candidates_and_lists_the_printed_keys",
        "Rank",
        literal_required=(
            "Leave out candidates that edited the plan file.",
            (
                "`rank` prints `winner`, `order`, `rank`, `scenarios_met`, "
                "`disqualified`, and `reasons`."
            ),
        ),
    ),
    Fact(
        "rank_with_no_candidate_left_is_a_null_winner_and_does_not_run",
        "Rank",
        literal_required=(
            "If no candidate is left to rank, treat it as a `null` winner.",
            "Do not run `rank`.",
        ),
    ),
    Fact(
        "record_names_the_script_attempt_and_runs_before_and_after_keep",
        "Record",
        literal_required=(
            'plan_summary_record.py" record',
            "--attempt <k>",
            "`record` runs before Keep.",
            "Run it again with the same attempt after Keep",
        ),
    ),
    Fact(
        "record_row_schema_is_the_candidate_dict_plus_rank_outcome_and_reason",
        "Record",
        literal_required=(
            "Each row is the candidate dict plus `rank`, `outcome`, and `reason`.",
            "Take `rank[<i>]` from the output of `rank`.",
            "A `not dispatched` row carries only `id`, `outcome`, and `reason`.",
        ),
    ),
    Fact(
        "record_provisional_kept_row_carries_the_reconcile_pending_reason",
        "Record",
        literal_required=(
            "- The winner is `kept`, with the reason `provisional (reconcile pending)`.",
        ),
    ),
    Fact(
        "record_gives_a_plan_file_edited_candidate_a_rank_after_the_last_ranked",
        "Record",
        literal_required=(
            (
                "Give a plan-file-edited candidate a rank after the last ranked one, "
                "in id order."
            ),
            "With no ranked candidate, those ranks start at 1.",
        ),
    ),
    Fact(
        "record_undispatched_reason_depends_on_stop_or_halt",
        "Record",
        literal_required=(
            (
                "An undispatched candidate is `not dispatched`. "
                "Its reason is `cost cap` after a `stop` "
                "and `halted before dispatch` after a halt."
            ),
        ),
    ),
    Fact(
        "record_defines_removed_as_not_kept_with_the_branch_kept_until_cleanup",
        "Record",
        literal_required=(
            "`removed` means the candidate is not kept.",
            "Its branch stays until Cleanup.",
        ),
    ),
    Fact(
        "record_states_both_unranked_outcomes_as_disqualified",
        "Record",
        literal_required=(
            (
                "A no-commits candidate and a plan-file-edited candidate "
                "are `disqualified`."
            ),
        ),
    ),
    Fact(
        "record_disqualified_reason_comes_from_rank_except_the_two_written_by_hand",
        "Record",
        literal_required=(
            "Its reason is `reasons[<i>]` from the output of `rank`.",
            "(`no commits`)",
            "(`plan file edited`)",
            "This reason replaces `reasons[<i>]`.",
        ),
    ),
    Fact(
        "keep_reconciles_with_restore_and_tries_the_next_non_disqualified_id",
        "Keep",
        literal_required=(
            'build_candidates.py" reconcile --repo',
            "restores the build branch on failure",
            "reconcile failed",
            "next non-disqualified id",
        ),
    ),
    Fact(
        "keep_passes_the_suite_with_equals_and_ends_options_before_the_branch",
        "Keep",
        literal_required=("--test-cmd='<suite>' -- '<winner-branch>'",),
    ),
    Fact(
        "keep_passes_a_quote_in_the_suite_command_as_quote_backslash_quote_quote",
        "Keep",
        literal_required=("Write an embedded `'` in `<suite>` as `'\\''`:",),
    ),
    Fact(
        "keep_counts_exit_1_as_reconcile_failed_only_with_merged_false_json",
        "Keep",
        literal_required=('Exit 1 with `"merged": false` in the JSON on stdout',),
    ),
    Fact(
        "keep_exit_2_is_a_restore_failure_only_when_stderr_names_the_sha",
        "Keep",
        literal_required=(
            "Exit 2 with the pre-merge SHA named on stderr: the restore failed.",
            "exit 2 without that SHA",
        ),
    ),
    Fact(
        "keep_any_other_non_zero_exit_is_a_script_failure",
        "Keep",
        literal_required=(
            (
                "Exit 1 without that JSON, exit 2 without that SHA, "
                "or any other non-zero exit: the script failed."
            ),
        ),
    ),
    Fact(
        "keep_halt_disqualifies_the_candidate_being_merged",
        "Keep",
        literal_required=(
            (
                "When `reconcile` exits non-zero and Keep halts, the candidate "
                "being merged is `disqualified`. "
                "Its reason is `reconcile halted: <halt reason>`."
            ),
            "The halt template names its branch to merge by hand.",
            "A halt after exit 0 leaves the merged winner `kept`, with an empty reason.",
            "The last candidate keeps the reason `reconcile failed`.",
        ),
    ),
    Fact(
        "keep_fills_test_files_staged_with_the_steps_test_files",
        "Keep",
        literal_required=(
            (
                "Fill `test_files_staged` with the step's test files, "
                "as `/build`'s TEST → REFACTOR transition does."
            ),
            "git diff --name-only <base>..HEAD",
            "Keep the test files. Stage them without placing their names in a shell line.",
            "git diff -z --name-only <base>..HEAD -- '<test pathspecs>' | xargs -0 git add --",
            '"test_files_staged": ["<test file>", "..."]',
        ),
    ),
    Fact(
        "keep_defines_winner_after_keep_as_the_merged_candidate",
        "Keep",
        literal_required=(
            "After Keep, `winner` means the candidate that `reconcile` merged.",
        ),
    ),
    Fact(
        "keep_rewrites_the_parent_build_phase_to_refactor_after_a_merge",
        "Keep",
        literal_required=(
            "After exit 0, rewrite the parent's `.claude/memory/build-phase.json`",
            "`phase: refactor`",
        ),
    ),
    Fact(
        "keep_final_record_marks_the_merged_candidate_kept_with_an_empty_reason",
        "Keep",
        literal_required=(
            "The merged candidate is `kept`, with an empty reason.",
            "Each candidate that failed to reconcile is `disqualified`",
            "Every other row is unchanged.",
            "A halt's record carries these final outcomes for every row.",
            "No provisional row survives a halt.",
        ),
    ),
    Fact(
        "resume_continues_at_the_inline_checkpoint_on_the_merged_winner",
        "Resume",
        literal_required=("sub-step 4's inline checkpoint on the merged winner",),
    ),
    Fact(
        "cleanup_runs_after_the_inline_checkpoint_and_is_idempotent",
        "Cleanup",
        literal_required=(
            'build_candidates.py" cleanup --repo',
            "List every accepted candidate branch, including the kept one.",
            "`/build` runs it after the step's inline checkpoint passes",
            "idempotent",
        ),
    ),
    Fact(
        "failure_modes_every_halt_writes_the_record_and_removes_nothing",
        "Failure modes",
        literal_required=("writes the record, removes nothing",),
    ),
    Fact(
        "failure_modes_template_names_the_halt_reason_and_fills_it_from_the_list",
        "Failure modes",
        literal_required=(
            "speculative dispatch halted at step <step>, attempt <k>: <halt reason>",
            "Fill `<halt reason>` with one of the reasons below.",
            "Preconditions halts are not template reasons.",
        ),
    ),
    Fact(
        "failure_modes_template_lists_the_preserved_candidates_with_a_row_reason",
        "Failure modes",
        literal_required=(
            "candidates preserved:",
            "<i> <branch> <worktree> <outcome> (<row reason>)",
        ),
    ),
    Fact(
        "failure_modes_template_carries_the_manual_merge_line",
        "Failure modes",
        literal_required=(
            "merge one by hand: python3",
            (
                "build_candidates.py\" reconcile --repo '<build-worktree>' "
                "--into '<build-branch>' --base <base> --test-cmd='<suite>' "
                "-- '<branch>' (restores the branch if the suite fails)"
            ),
        ),
    ),
    Fact(
        "failure_modes_template_carries_the_discard_line",
        "Failure modes",
        literal_required=(
            "discard them: python3",
            (
                "build_candidates.py\" cleanup --repo '<build-worktree>' "
                "--remove '<branch-1>' '<branch-2>'"
            ),
        ),
    ),
    Fact(
        "failure_modes_template_carries_the_rerun_line_naming_attempt_k_plus_1",
        "Failure modes",
        literal_required=(
            "re-running /build starts attempt <k+1> and spends the cap again",
        ),
    ),
    Fact(
        "failure_modes_template_carries_the_after_merging_by_hand_line",
        "Failure modes",
        literal_required=(
            (
                "after merging by hand: tick Step <step> in the plan's Build Progress, "
                "run the discard line, then re-run /build "
                "(it resumes at the first unticked step)"
            ),
        ),
    ),
    Fact(
        "failure_modes_template_suite_takes_keeps_quote_escape",
        "Failure modes",
        literal_required=(
            "Fill `<suite>` with the same `'\\''` escape that Keep uses.",
        ),
    ),
    Fact(
        "failure_modes_general_rule_keeps_collected_dicts_for_dispatched_candidates",
        "Failure modes",
        literal_required=(
            "Apply this rule to any halt before Rank:",
            "A dispatched candidate keeps its `collect` dict or its no-commits dict.",
        ),
    ),
    Fact(
        "failure_modes_general_rule_gives_an_interrupted_candidate_the_no_commits_shape",
        "Failure modes",
        literal_required=(
            (
                "A candidate the halt interrupted before `collect` takes the "
                "no-commits dict shape."
            ),
            "It has `suite_green` false, every scenario unmet, and zero counts.",
            (
                "Its `cost_usd` is `delta / width`, or 0 when `now` was not read. "
                "Its branch is the accepted one, or empty."
            ),
        ),
    ),
    Fact(
        "failure_modes_general_rule_ranks_in_id_order_and_marks_undispatched",
        "Failure modes",
        literal_required=(
            "- Assign ranks in id order.",
            (
                "- Every undispatched candidate is `not dispatched` "
                "with the reason `halted before dispatch`."
            ),
        ),
    ),
    Fact(
        "failure_modes_null_winner_names_the_top_of_order",
        "Failure modes",
        literal_required=(
            (
                "`no candidate has a green suite and parseable screening`: "
                "`rank` ran and printed a `null` winner. "
                "Name the top of `order` as the branch to inspect."
            ),
        ),
    ),
    Fact(
        "failure_modes_nothing_left_to_rank_names_no_branch",
        "Failure modes",
        literal_required=(
            "`no candidate was left to rank`: every dispatched candidate edited the plan file.",
            "No `order` exists.",
            "The template lists the preserved candidates and names no branch.",
        ),
    ),
    Fact(
        "failure_modes_lists_the_reconcile_reasons",
        "Failure modes",
        literal_required=(
            "`every ranked candidate failed to reconcile`",
            (
                "`build branch could not be restored after a failed reconcile "
                "(git reset --keep <sha> by hand)`"
            ),
        ),
    ),
    Fact(
        "failure_modes_keep_halt_reason_is_a_row_reason_not_a_template_reason",
        "Failure modes",
        literal_required=(
            (
                "On a Keep halt, the template carries the specific reason. "
                "The merged candidate's row carries "
                "`reconcile halted: <that reason>`."
            ),
        ),
        literal_forbidden=("`reconcile halted: <halt reason>`: Keep halted",),
    ),
    Fact(
        "failure_modes_lists_the_no_spend_reason",
        "Failure modes",
        literal_required=(
            "`cost meter recorded no spend for the last batch`: `project` printed `halt`.",
        ),
    ),
    Fact(
        "failure_modes_script_failure_reason_covers_every_halting_command",
        "Failure modes",
        literal_required=(
            "`<command> exited non-zero`: add the stderr.",
            (
                "`cost_meter.py`, `build_candidates.py`, `plan_summary_record.py`, "
                "`build_slice_scope.py`, `build_jobs.py`, and git `hash-object`, "
                "`diff`, `cat-file`, and `worktree list`."
            ),
        ),
    ),
    Fact(
        "failure_modes_lists_the_dispatch_failure_reason",
        "Failure modes",
        literal_required=(
            "`candidate <i> dispatch failed`",
            "the worktree could not be created, or the agent returned an error",
        ),
    ),
    Fact(
        "failure_modes_does_not_list_agent_unavailable_as_a_template_reason",
        "Failure modes",
        literal_forbidden=("Agent tool unavailable",),
    ),
    Fact(
        "failure_modes_plan_file_changed_states_the_row_outcomes",
        "Failure modes",
        literal_required=(
            (
                "`plan file changed during batch <b> "
                "(changed file saved as <plan>.batch-<b>)`"
            ),
            "every candidate of that batch is `disqualified` with that reason",
            (
                "Candidates of earlier batches are `removed` "
                "with the reason `halted before rank`."
            ),
            "Because `rank` did not run, assign ranks in id order.",
        ),
    ),
    Fact(
        "failure_modes_plan_file_changed_keeps_the_own_reason_of_unranked_candidates",
        "Failure modes",
        literal_required=(
            (
                "A no-commits or plan-file-edited candidate keeps `disqualified` "
                "with its own reason."
            ),
        ),
    ),
    Fact(
        "failure_modes_cap_line_prints_only_after_a_stop_after_the_first_line",
        "Failure modes",
        literal_required=(
            (
                "When `project` printed `stop`, add this line "
                "after the first line of the template:"
            ),
            (
                "`only <dispatched> of <N> candidates were dispatched (cost cap); "
                "raise --max-cost-usd to try more`"
            ),
        ),
    ),
    Fact(
        "failure_modes_record_failure_prints_the_template_with_the_stderr_line",
        "Failure modes",
        literal_required=(
            (
                "When the halt's own `record` call exits non-zero, "
                "print the template anyway."
            ),
            "Add the line `record not written: <stderr>` after the first line.",
        ),
    ),
    Fact(
        "failure_modes_distinguish_a_red_suite_from_an_unparseable_lens",
        "Failure modes",
        literal_required=(
            (
                "A red suite and an unparseable lens are distinguished "
                "in the Reason column."
            ),
        ),
    ),
    Fact(
        "failure_modes_cleanup_failure_is_not_a_halt",
        "Failure modes",
        literal_required=(
            "A `cleanup` failure after the checkpoint is not a halt.",
            "The failure does not undo the step.",
        ),
    ),
]


@pytest.mark.parametrize("fact", FACTS, ids=lambda f: f.id)
def test_skill_section_states(skill_text, fact):
    assert_fact(SECTIONS, skill_text, fact)


def test_registry_lists_the_skill_in_the_skills_registry():
    registry = section(
        REGISTRY.read_text(encoding="utf-8"),
        r"^## Skills Registry$",
        boundary_pattern=r"^## ",
    )
    assert grep(
        r"^\| Speculative Build \| `skills/speculative-build/SKILL\.md` "
        r"\| ~[0-9,]+ \| `/build` command \|$",
        registry,
    )


def test_skills_doc_lists_the_skill_as_agent_loaded():
    rows = [
        ln
        for ln in SKILLS_DOC.read_text(encoding="utf-8").splitlines()
        if "speculative-build/SKILL.md" in ln
    ]
    assert len(rows) == 1
    assert rows[0].startswith("| speculative-build | agent-loaded")
