"""Doc-shape contract for speculative-build/SKILL.md (plan Slice 3, Step 3.1).

The skill is a procedure `/build --candidates N` follows for one `complex`
step. These tests pin the contract the plan's Slice 3 Gherkin names: the
frontmatter, the twelve sections in order, and the phrases each section must
carry. Registration is checked last: the registry row and the `docs/skills.md`
row. The exit codes of `check_registry_sync.py` and `build_skills_index.py
--check` are already gated by `tests/repo/test_registry_sync.py` and
`tests/repo/test_skills_index_current.py`.
"""

from __future__ import annotations

import re
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
    "<winner-branch>",
    "<build-branch>",
    "<worktree>",
    "<build-worktree>",
)


@pytest.fixture(scope="module")
def skill_text() -> str:
    return SKILL.read_text(encoding="utf-8")


def _h2(name: str) -> Callable[[str], str]:
    """Resolve a `## <name>` section of the skill, up to the next `## `."""
    return lambda text: section(text, rf"^## {name}$", boundary_pattern=r"^## ")


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
    for block in _bash_blocks(skill_text):
        for line in block.splitlines():
            for match in re.finditer(re.escape(placeholder), line):
                start = match.start()
                assert start > 0 and line[start - 1] in "'=", (
                    f"{placeholder} is not single-quoted in: {line}"
                )


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
        "base_and_batches_open_with_the_six_step_batch_loop",
        "Base and batches",
        literal_required=(
            "1. Read `prev` from the cost meter.",
            "2. Dispatch the batch.",
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
                "engage <plan> --slice <id> --hooks-dir <your worktree>/.claude/hooks"
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
            "Use the reason `plan file edited`.",
            "Do not rank it.",
        ),
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
        "record_disqualified_reason_comes_from_rank_except_the_two_written_by_hand",
        "Record",
        literal_required=(
            "Its reason is `reasons[<id>]` from the output of `rank`.",
            "(`no commits`)",
            "(`plan file edited`)",
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
        "keep_counts_exit_1_as_reconcile_failed_only_with_merged_false_json",
        "Keep",
        literal_required=(
            'Exit 1 with `"merged": false` in the JSON on stdout',
            "Exit 1 without that JSON, or any other non-zero exit: the script failed.",
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
            "A halt's record carries these final outcomes for every row.",
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
            "`/build` runs it after the step's inline checkpoint passes",
            "idempotent",
        ),
    ),
    Fact(
        "failure_modes_every_halt_writes_the_record_and_removes_nothing",
        "Failure modes",
        literal_required=("writes the record, removes nothing",),
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
