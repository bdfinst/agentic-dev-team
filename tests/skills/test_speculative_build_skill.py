"""Doc-shape contract for speculative-build/SKILL.md (issue #2273, plan
Slice 3, Step 3.1).

The skill is a procedure `/build --candidates N` follows for one `complex`
step. These tests pin the contract the plan's Slice 3 Gherkin names: the
frontmatter, the twelve sections in order, and the phrases each section must
carry. Registration (agent-registry row, regenerated docs/skills.md) is
checked last.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable

import pytest
from skill_doc_helpers import (
    PLUGIN_ROOT,
    REPO_ROOT,
    Fact,
    assert_fact,
    collapsed,
    frontmatter,
    grep,
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


def _h2_headings(text: str) -> list[str]:
    """`## ` headings outside fenced code blocks, in file order."""
    headings: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
        elif not in_fence and line.startswith("## "):
            headings.append(line[3:].strip())
    return headings


def test_skill_frontmatter_declares_name_and_orchestrator_role(skill_text):
    fm = frontmatter(skill_text)
    assert grep(r"^name: speculative-build$", fm)
    assert grep(r"^role: orchestrator$", fm)


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
    assert _h2_headings(skill_text) == SECTION_ORDER


def test_skill_body_opens_with_one_h1_before_the_sections(skill_text):
    lines = [ln for ln in skill_text.splitlines() if ln.startswith("# ")]
    assert lines == ["# Speculative Build (#2273)"]
    assert skill_text.index(lines[0]) < skill_text.index("## Preconditions")


def test_skill_names_no_model(skill_text):
    assert not grep(r"opus|sonnet|haiku|fable", skill_text, ignore_case=True)


FACTS = [
    # Preconditions and batching
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
        "preconditions_halt_when_invoked_outside_build",
        "Preconditions",
        literal_required=(
            (
                "halt with `speculative dispatch requires a session transcript, "
                "worktree.baseRef = head and validated flags; run /build, not this skill`"
            ),
            "This skill halts when you invoke it outside `/build`.",
        ),
    ),
    Fact(
        "batch_1_is_candidate_1_alone",
        "Base and batches",
        literal_required=("Make batch 1 candidate 1 alone",),
    ),
    Fact(
        "later_batches_are_sized_by_build_jobs_wave_width",
        "Base and batches",
        literal_required=("build_jobs.py", "--wave-width"),
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
        "dispatch_freeze_is_engaged_against_the_candidate_hooks_dir",
        "Dispatch",
        literal_required=(
            "engage it per candidate before dispatch",
            "candidate worktree's hooks dir",
            "--hooks-dir <candidate-worktree>/.claude/hooks",
        ),
    ),
    Fact(
        "dispatch_only_the_parent_writes_the_plan_file",
        "Dispatch",
        literal_required=("Only the parent writes the plan file.",),
    ),
    Fact(
        "dispatch_branch_is_read_from_the_result_and_confirmed_with_worktree_list",
        "Dispatch",
        literal_required=("`branch:` line of the dispatch result", "git worktree list"),
    ),
    Fact(
        "dispatch_without_commits_is_a_candidate_with_suite_green_false",
        "Dispatch",
        literal_required=(
            "no-commits candidate",
            "`suite_green` false",
            "the reason `no commits`",
            "It is not a halt.",
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
        "screening_names_both_lenses_json_categories_and_collect",
        "Screening",
        literal_required=(
            "spec-compliance-review",
            "correctness-review",
            "--json",
            "uncovered-scenario",
            "unmet-criterion",
            "collect",
        ),
    ),
    Fact(
        "screening_says_the_winner_is_screened_again_by_design",
        "Screening",
        literal_required=("The winner is therefore screened again by design.",),
    ),
    # Cost cap
    Fact(
        "cost_cap_names_the_meter_the_projection_and_the_outcomes",
        "Cost cap",
        literal_required=(
            'cost_meter.py" report --transcript',
            "--json",
            "totals.cost_usd",
            'build_candidates.py" project',
            "--last-batch-delta",
            "delta / width",
            "not dispatched",
            "cost cap",
            "halt",
        ),
    ),
    Fact(
        "cost_cap_reads_the_meter_right_after_dispatch_before_suite_and_screening",
        "Cost cap",
        literal_required=(
            "Read `now` immediately after the batch's dispatches return.",
            "Read it before Suite and diff and before Screening.",
        ),
    ),
    Fact(
        "cost_cap_projects_before_every_batch_after_the_first_never_inside_one",
        "Cost cap",
        literal_required=(
            (
                "`project` runs before every batch after the first, "
                "while candidates remain."
            ),
            "It never runs inside a batch.",
        ),
    ),
    Fact(
        "cost_cap_per_candidate_cost_is_the_batch_delta_over_the_width",
        "Cost cap",
        literal_required=("`cost_usd = delta / width`",),
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
            "projected $<P>, <decision>",
            "no candidates remain",
        ),
    ),
    # Record, Keep, Cleanup, Resume
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
        "record_provisional_kept_row_carries_the_reconcile_pending_reason",
        "Record",
        literal_required=("provisional (reconcile pending)",),
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


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_registry_lists_the_skill_in_the_skills_registry():
    registry = section(
        REGISTRY.read_text(encoding="utf-8"),
        r"^## Skills Registry$",
        boundary_pattern=r"^## ",
    )
    assert grep(
        r"^\| Speculative Build \| `skills/speculative-build/SKILL\.md` \| ~[0-9,]+ \|",
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


def test_registry_sync_check_exits_zero():
    result = _run("scripts/check_registry_sync.py")
    assert result.returncode == 0, result.stdout + result.stderr


def test_skills_index_check_exits_zero():
    result = _run("plugins/dev-team/hooks/lib/build_skills_index.py", "--check")
    assert result.returncode == 0, result.stdout + result.stderr
