"""Doc-shape contract for autoship/SKILL.md (issue #2099: consolidated from
100 one-fact-one-function tests into one parametrized table — see
`skill_doc_helpers.Fact`/`assert_fact` for the shared mechanism and
tests/skills/test_fix_skill.py for its sibling conversion).

Originally written for plan slice 3 (autoship-issue-batching, Step 3.1):
autoship/SKILL.md's Step 2 must document the two-stage
`autoship_group.py` -> `autoship_queue.py` pipeline instead of the old
single `autoship_discover.py` call. Also covers Slice 4 (leftover
grouping/confirmation), Slice 6 (batch dispatch via `/ship --issues`), and
issue #2073 (`--max-batch-size` cross-validation).

A handful of facts don't fit the table's (pattern, section) shape --
ordering between two positions, a substring-count assertion, or a single
test mixing collapsed and raw section text for different assertions -- and
stay as their own functions below the table, using the same cached
`skill_text` fixture.
"""

from __future__ import annotations

import pytest
from skill_doc_helpers import (
    PLUGIN_ROOT,
    Fact,
    assert_fact,
    collapsed,
    frontmatter,
    grep,
    parse_arguments_section,
    section,
)

AUTOSHIP = PLUGIN_ROOT / "skills" / "autoship"
SKILL = AUTOSHIP / "SKILL.md"


@pytest.fixture(scope="module")
def skill_text() -> str:
    return SKILL.read_text()


def _step_1(t: str) -> str:
    return section(t, r"^## Step 1", boundary_pattern=r"^## Step 2")


def _step_2(t: str) -> str:
    return section(t, r"^## Step 2", boundary_pattern=r"^## Step 3")


def _step_2b(t: str) -> str:
    return section(t, r"^### Step 2b", boundary_pattern=r"^### Step 2c")


def _step_2c(t: str) -> str:
    return section(t, r"^### Step 2c", boundary_pattern=r"^## Step 3")


def _step_3(t: str) -> str:
    return section(t, r"^## Step 3", boundary_pattern=r"^## Step 4")


def _step_3b(t: str) -> str:
    return section(_step_3(t), r"^### 3b", boundary_pattern=r"^### 3c")


def _step_3c(t: str) -> str:
    return section(_step_3(t), r"^### 3c", boundary_pattern=r"^### 3d")


def _step_3d(t: str) -> str:
    return section(_step_3(t), r"^### 3d ", boundary_pattern=r"^### 3d\.1")


def _step_3d1(t: str) -> str:
    return section(_step_3(t), r"^### 3d\.1", boundary_pattern=r"^### 3e ")


def _step_3e(t: str) -> str:
    return section(_step_3(t), r"^### 3e ", boundary_pattern=r"^### 3e\.1")


def _step_3f(t: str) -> str:
    return section(_step_3(t), r"^### 3f", boundary_pattern=r"^## Step 4")


def _step_4(t: str) -> str:
    return section(t, r"^## Step 4", boundary_pattern=r"^## Notes")


SECTIONS = {
    "full": lambda t: t,
    "frontmatter": frontmatter,
    "parse_arguments": parse_arguments_section,
    "step_1": _step_1,
    "step_2": _step_2,
    "step_2b": _step_2b,
    "step_2c": _step_2c,
    "step_3": _step_3,
    "step_3b": _step_3b,
    "step_3c": _step_3c,
    "step_3d": _step_3d,
    "step_3d1": _step_3d1,
    "step_3e": _step_3e,
    "step_3f": _step_3f,
    "step_4": _step_4,
}


FACTS = [
    Fact(
        "step_2_no_longer_documents_single_discover_call_feeding_loop",
        "step_2",
        forbidden=[(r"autoship_discover\.py \\\s*\n\s*--max-issues", False)],
        collapse=False,
    ),
    Fact(
        "step_2_names_discover_script_as_no_longer_part_of_pipeline",
        "step_2",
        required=[
            (r"autoship_discover\.py.*not.*part of this pipeline", False),
            (r"do not modify or remove that script", False),
        ],
    ),
    Fact(
        "step_2_documents_group_script_fetches_full_pool_without_max_issues_cap",
        "step_2",
        required=[
            (r"self-fetches the \*\*full\*\* eligible pool", False),
            (r"no `--max-issues` truncation at that layer", False),
        ],
    ),
    Fact(
        "step_2_documents_label_flag_flows_to_group_script",
        "step_2",
        required=[
            (
                (r"flows to `autoship_group\.py --label\s*<label>` instead of "
                r"`autoship_discover\.py --label <label>`"),
                False,
            )
        ],
    ),
    Fact(
        "step_2_documents_empty_queue_stop_message",
        "step_2",
        required=[
            (r"both `queue` and `deferred` empty", False),
            (r"No eligible issues found this round\.", False),
        ],
    ),
    Fact(
        "step_2_documents_dry_run_prints_queue_and_stops",
        "step_2",
        required=[(r"--dry-run.*mode, print the discovered queue and stop here", False)],
    ),
    Fact(
        "step_2_dry_run_stop_line_uses_per_dispatch_unit_wording",
        "step_2",
        required=[
            (r"stop here without\s*proceeding to per-dispatch-unit processing", False)
        ],
        forbidden=[(r"per-issue processing", False)],
    ),
    Fact(
        "role_description_uses_per_dispatch_unit_not_per_issue",
        "full",
        literal_required=["pipeline per dispatch unit and logs each outcome"],
        literal_forbidden=["pipeline per issue and logs each outcome"],
        collapse=False,
    ),
    Fact(
        "step_2_no_longer_names_a_step_3_transition_gap",
        "step_2",
        forbidden=[
            (
                (r"Step 3's prose below is still written for the old "
                r"`\{number, title\}` shape"),
                False,
            )
        ],
        required=[
            (
                (r"Step 3 processes this\s*queue directly, one dispatch unit at a "
                r"time, in order"),
                False,
            )
        ],
    ),
    Fact(
        "step_2_documents_empty_queue_nonempty_deferred_branch",
        "step_2",
        required=[
            (r"`queue` is empty but `deferred` is \*\*not\*\* empty", False),
            (r"No dispatchable unit fits --max-issues <N> this round", False),
            (r"unit\(s\) deferred\s*whole", False),
            (r"do not.*silently fall through to Step 3", True),
        ],
    ),
    Fact(
        "step_4_round_summary_includes_deferred_count",
        "step_4",
        required=[(r"Deferred\s*:\s*<N> unit\(s\), <M> issue\(s\)", False)],
    ),
    Fact(
        "step_4_round_summary_json_distinguishes_units_from_issues",
        "step_4",
        required=[
            (r'"deferred_units":\s*<N>', False),
            (r'"deferred_issues":\s*<M>', False),
        ],
        forbidden=[(r'"deferred":\s*<N>', False)],
    ),
    Fact(
        "step_4_status_enum_covers_both_early_exit_stops",
        "step_4",
        required=[(r'"no_eligible_issues"', False), (r'"no_unit_fits_cap"', False)],
    ),
    Fact(
        "step_2_early_exits_record_the_new_status_values",
        "step_2",
        required=[
            (r'status:\s*"no_eligible_issues"', False),
            (r'status:\s*"no_unit_fits_cap"', False),
        ],
    ),
    Fact(
        "step_2_documents_discovery_pipe_failure_is_fatal",
        "step_2",
        required=[
            (r"a discovery failure is fatal for the round", False),
            (r"the actionable error is the `autoship_group:`-prefixed", False),
            (r"autoship_queue\.py.*will report its own unrelated", False),
        ],
    ),
    Fact(
        "step_3_no_longer_opens_with_the_shape_mismatch_disclaimer",
        "step_3",
        forbidden=[
            (
                (r"this step's prose still assumes the old `\{number, title\}` "
                r"per-issue shape"),
                False,
            )
        ],
    ),
    Fact(
        "step_3_processes_queue_array_dispatch_units_directly",
        "step_3",
        required=[
            (
                (r"each a \*\*dispatch unit\*\*, either\s*"
                r'`\{"type": "batch", "batch_id": \.\.\., "issues": \[n1, n2, \.\.\.\]\}`'),
                False,
            ),
            (r'`\{"type": "solo", "issue": N\}`', False),
            (r"strictly in order", True),
        ],
    ),
    Fact(
        "step_1_no_longer_claims_reclaim_affects_max_issues_accounting",
        "step_1",
        forbidden=[(r"so they are not counted against", False)],
    ),
    Fact(
        "step_1_states_corrected_reclaim_rationale",
        "step_1",
        required=[
            (r"does not change `--max-issues`\s*accounting", False),
            (r"autoship_state\.is_eligible", False),
            (
                r"real purpose is unsticking issues orphaned by a crashed round",
                False,
            ),
        ],
    ),
    Fact(
        "parse_arguments_documents_max_batch_size_flag",
        "parse_arguments",
        required=[(r"--max-batch-size N", False)],
    ),
    Fact(
        "usage_string_agrees_with_argument_hint_on_max_batch_size",
        "parse_arguments",
        required=[
            (r"Usage: /autoship.*--max-batch-size N", False),
            (r"default:\s*5", False),
        ],
    ),
    Fact(
        "frontmatter_argument_hint_includes_max_batch_size",
        "frontmatter",
        required=[(r"\[--max-batch-size N\]", False)],
        collapse=False,
    ),
    Fact(
        "parse_arguments_documents_max_batch_size_cap_cross_validation",
        "parse_arguments",
        required=[
            (
                r"Cross-validate `--max-batch-size` against `--max-issues` \(#2073\)",
                False,
            ),
            (
                (r"greater\s*than `--max-issues`, print this message and stop, without "
                r"proceeding to\s*Step 1"),
                False,
            ),
        ],
    ),
    Fact(
        "parse_arguments_max_batch_size_cap_stop_message_matches_usage_style",
        "parse_arguments",
        required=[(r"Usage: /autoship.*--max-batch-size N", False)],
        literal_required=[
            "autoship: --max-batch-size <B> cannot exceed --max-issues <N>."
        ],
        collapse=False,
    ),
    Fact(
        "step_2b_exists_after_step_2_pipeline",
        "step_2",
        literal_required=["### Step 2b"],
        collapse=False,
    ),
    Fact(
        "step_2b_documents_one_agent_dispatch_per_round_not_per_issue",
        "step_2b",
        required=[
            (r"dispatch \*\*exactly one agent\*\* for this round", False),
            (r"never one agent dispatch per ungrouped issue", False),
        ],
    ),
    Fact(
        "step_2b_documents_zero_ungrouped_no_op_case",
        "step_2b",
        required=[
            (r"Fewer than two ungrouped issues.*skip this stage entirely", False),
            (r"No agent is dispatched\s*this round at all", False),
        ],
    ),
    Fact(
        "step_2b_documents_two_or_more_threshold_for_dispatch",
        "step_2b",
        required=[
            (r"\*\*Two or more ungrouped issues\*\*: dispatch", False),
            (r"\(zero, or exactly one\)", False),
        ],
    ),
    Fact(
        "step_2b_documents_oversized_proposal_trim_rule",
        "step_2b",
        required=[
            (r"to its oldest `--max-batch-size` members by the SAME rule", True),
            (r"oldest-first", False),
            (r"overflow returns to ungrouped rather than being dropped", False),
        ],
    ),
    Fact(
        "step_2b_documents_untaken_issues_proceed_as_solo",
        "step_2b",
        required=[
            (
                (r"remain ungrouped and proceed to `autoship_queue\.py` as solo "
                r"dispatch\s*units, exactly as today"),
                False,
            )
        ],
    ),
    Fact(
        "step_2c_documents_block_applies_blocked_and_removes_ready",
        "step_2c",
        required=[
            (
                (r"label EVERY member issue `autoship:blocked`, removing\s*"
                r"`autoship:ready` in the same operation"),
                False,
            )
        ],
    ),
    Fact(
        "step_2c_documents_comment_required_content",
        "step_2c",
        required=[
            (r"The grouping rationale", False),
            (r"Every member issue number in the proposed batch", False),
            (
                (r"gh issue edit <n1> <n2> \.\.\. --add-label autoship:batch-confirmed "
                r"--remove-label autoship:blocked --add-label autoship:ready"),
                False,
            ),
        ],
    ),
    Fact(
        "step_2c_documents_confirm_outcome_partial_supported",
        "step_2c",
        required=[
            (r"partial confirmation is explicitly supported, not an error", False),
            (
                (r"Whichever subset of the ORIGINAL proposal ends up carrying\s*"
                r"`autoship:batch-confirmed` is what the NEXT round's deterministic "
                r"grouping\s*pass groups"),
                True,
            ),
        ],
    ),
    Fact(
        "step_2c_documents_reject_outcome_returns_to_solo_eligibility",
        "step_2c",
        required=[
            (r"WITHOUT\s*adding `autoship:batch-confirmed`", True),
            (
                (r"returns to plain solo eligibility next round and is NOT "
                r"re-proposed as part\s*of the same batch"),
                True,
            ),
        ],
    ),
    Fact(
        "step_2c_documents_label_transition_atomicity_rule",
        "step_2c",
        required=[
            (
                (r"applying `autoship:blocked` always removes\s*`autoship:ready` in "
                r"the same operation"),
                False,
            ),
            (
                (r"applying\s*`autoship:batch-confirmed` \+ `autoship:ready` always "
                r"removes\s*`autoship:blocked` in the same operation"),
                False,
            ),
        ],
    ),
    Fact(
        "step_2c_documents_batch_confirmed_and_ready_coexist",
        "step_2c",
        required=[
            (
                (r"`autoship:batch-confirmed`\s*and `autoship:ready` DO co-occur "
                r"together once a batch is confirmed"),
                True,
            )
        ],
    ),
    Fact(
        "step_2c_documents_blocked_mutual_exclusivity_clause",
        "step_2c",
        required=[
            (
                (r"never co-present with\s*`autoship:ready` or with "
                r"`autoship:batch-confirmed`"),
                False,
            )
        ],
    ),
    Fact(
        "step_2_documents_confirmed_batch_members_resolution_note",
        "step_2",
        required=[
            (r"Resolving `confirmed_batch_members`", False),
            (r"gh issue view <n> --json comments", False),
        ],
    ),
    Fact(
        "step_2_documents_gh_absent_confirmed_batch_members_known_gap",
        "step_2",
        required=[
            (r"Known gap, gh-absent `confirmed_batch_members` only", False),
            (r"no call that returns an issue's comment bodies", False),
        ],
    ),
    Fact(
        "step_2c_documents_removing_batch_members_from_ungrouped_array",
        "step_2c",
        required=[
            (
                (r"delete every member of every proposed batch \*\*that was actually\s*"
                r"BLOCKED above\*\*\s*from\s*`<scratch-grouping\.json>`'s `ungrouped` array"),
                False,
            ),
            (r"must not be dispatched solo or in any batch this round", False),
        ],
    ),
    Fact(
        "step_2c_documents_hidden_batch_members_marker",
        "step_2c",
        required=[(r"<!-- autoship-batch-members: <n1>,<n2>,\.\.\. -->", False)],
    ),
    Fact(
        "step_2c_documents_marker_idempotency_check",
        "step_2c",
        required=[
            (r"\*\*Idempotency\*\*", False),
            (r"skip posting", False),
            (r"never re-post an equivalent proposal comment", False),
        ],
    ),
    Fact(
        "step_2c_confirm_outcome_names_the_actual_mechanism",
        "step_2c",
        required=[
            (r"has_batch_confirmed_override", False),
            (r"confirmed_batch_members.*marker", False),
        ],
    ),
    Fact(
        "step_2b_documents_dry_run_guard",
        "step_2b",
        required=[
            (r"\*\*Dry-run guard\.\*\*", False),
            (r"skip the agent dispatch entirely", False),
        ],
    ),
    Fact(
        "step_2c_documents_dry_run_guard",
        "step_2c",
        required=[
            (r"\*\*Dry-run guard\.\*\*", False),
            (r"skip every mutation below", False),
        ],
    ),
    Fact(
        "step_2b_names_autoship_batch_proposer_agent_dispatched_via_task_tool",
        "step_2b",
        required=[
            (r"via the `Task`\s*tool, subagent type `autoship-batch-proposer`", False)
        ],
        forbidden=[(r"subagent type `general-purpose`", False)],
    ),
    Fact(
        "frontmatter_allowed_tools_includes_task",
        "frontmatter",
        required=[(r"\bTask\b", False)],
        collapse=False,
    ),
    Fact(
        "step_2b_documents_agent_output_json_schema",
        "step_2b",
        literal_required=[
            '{"proposals": [{"rationale": "...", "issues": [101, 102]}]}'
        ],
        collapse=False,
    ),
    Fact(
        "step_2b_documents_response_validation_rules",
        "step_2b",
        required=[
            (r"not present in the current\s*`ungrouped` set", False),
            (r"appears in more than one proposal", False),
            (r"keeping only\s*its FIRST occurrence", True),
            (r"fewer than 2 members after steps 1-3", False),
            (r"treat it as zero proposals", False),
        ],
    ),
    Fact(
        "step_2b_documents_cost_cap_check_before_dispatch",
        "step_2b",
        required=[
            (r"\*\*Cost-cap check \(before dispatch\)\.\*\*", False),
            (r"/cost-report", False),
            (r"skip the agent dispatch entirely", False),
            (r"counts against `--max-cost-usd` like everything else", False),
        ],
    ),
    Fact(
        "step_2c_documents_issue_number_validation",
        "step_2c",
        required=[(r"rejected in\s*its entirety", False)],
        literal_required=[r"^[0-9]+$"],
    ),
    Fact(
        "step_2c_documents_body_file_usage_not_inline_body",
        "step_2c",
        required=[(r"--body-file", False), (r"never inline `--body", False)],
        literal_required=["--body-file <scratch-comment-file>"],
    ),
    Fact(
        "step_2c_documents_gh_absent_block_mechanism",
        "step_2c",
        required=[
            (r"mcp__github__issue_write.*method `update`.*per member issue", False)
        ],
    ),
    Fact(
        "step_2c_documents_gh_absent_comment_mechanism",
        "step_2c",
        required=[
            (r"mcp__github__add_issue_comment.*with the same composed body", False)
        ],
    ),
    Fact(
        "step_2c_scopes_removal_to_batches_actually_blocked",
        "step_2c",
        required=[
            (
                (r"delete every member of every proposed batch \*\*that was actually\s*"
                r"BLOCKED above\*\*"),
                False,
            ),
            (r"was never blocked", False),
            (
                (r"its members MUST stay in `ungrouped` and\s*proceed to "
                r"`autoship_queue\.py` as solo dispatch units"),
                False,
            ),
        ],
    ),
    Fact(
        "step_2b_documents_body_resolution_dual_path",
        "step_2b",
        required=[
            (r"Resolving each issue's body \(before dispatch\)", False),
            (r"gh issue view <n> --json title,body", False),
            (
                (r"mcp__github__issue_read.*\(method `get`, that issue\s*number\) per "
                r"currently-\s*ungrouped issue"),
                False,
            ),
        ],
    ),
    Fact(
        "step_2c_documents_idempotency_check_dual_path",
        "step_2c",
        required=[
            (r"gh issue view <n> --json comments.*per member issue", False),
            (
                (r"this skill's MCP toolset has no call that returns an issue's\s*"
                r"comment bodies"),
                False,
            ),
            (r"Post the proposal\s*comment unconditionally", False),
            (
                r"a duplicate proposal comment is the accepted\s*degradation in this mode",
                False,
            ),
        ],
    ),
    Fact(
        "step_2c_validation_enumeration_names_all_injection_sites",
        "step_2c",
        required=[
            (
                r"the `gh issue comment <n1> --body-file \.\.\.`\s*invocation itself",
                False,
            ),
            (
                r"the `<!-- autoship-batch-members: \.\.\. -->` marker values",
                False,
            ),
            (r"the `<scratch-grouping\.json>` ungrouped-array rewrite", False),
        ],
    ),
    Fact(
        "step_2c_marker_item_carries_already_validated_qualifier",
        "step_2c",
        required=[
            (r"member list \(already validated above\), appended after", False)
        ],
    ),
    Fact(
        "step_2_documents_marker_author_validation",
        "step_2",
        required=[
            (
                r"only extract it from a comment posted by this\s*skill's own actor",
                False,
            ),
            (
                r"filter `comments\[\]\.author\.login` against the\s*invoking bot/user identity",
                False,
            ),
        ],
    ),
    Fact(
        "step_2_documents_marker_value_validation",
        "step_2",
        required=[
            (
                (r"validate every parsed value matches `\^\[0-9\]\+\$` before merging it\s*"
                r"into `confirmed_batch_members`"),
                False,
            ),
            (r"drop the whole marker", False),
        ],
    ),
    Fact(
        "step_2c_documents_concurrency_caveat",
        "step_2c",
        required=[
            (r"not atomic\s*across concurrent `/autoship` invocations", False),
            (
                r"two overlapping rounds could\s*both pass the check before either posts",
                False,
            ),
            (r"accepted limitation", False),
            (r"existing \"Sequential\s*only\" constraint", False),
        ],
    ),
    Fact(
        "step_3a_stop_message_names_dispatch_unit_generically",
        "step_3",
        required=[
            (r"Stopping before <unit>", False),
            (
                (r"`<unit>` names the dispatch unit generically.*`issue #<number>` "
                r"for a solo\s*unit, or `batch <batch_id> \(issues #<n1>, #<n2>, "
                r"\.\.\.\)` for a batch unit"),
                False,
            ),
        ],
    ),
    Fact(
        "step_3b_documents_batch_multi_issue_label_in_progress",
        "step_3b",
        required=[
            (
                (r"label EVERY member issue `autoship:in-progress` together, in one\s*"
                r"operation"),
                False,
            ),
            (r"gh issue edit <n1> <n2> \.\.\. \\", False),
            (r"add-label autoship:in-progress", False),
        ],
    ),
    Fact(
        "step_3b_documents_solo_path_unchanged",
        "step_3b",
        required=[
            (r"\*\*Solo\*\* — unchanged from today's single-issue behavior", False)
        ],
    ),
    Fact(
        "step_3c_documents_batch_invokes_ship_once_with_issues_flag",
        "step_3c",
        required=[
            (
                (r"invoke `/ship` \*\*once\*\*, with `--issues <n1>,<n2>,\.\.\.` naming\s*"
                r"every member issue"),
                False,
            ),
            (r"--issues <n1>,<n2>,\.\.\. --no-auto-merge", False),
        ],
    ),
    Fact(
        "step_3c_batch_cites_ship_closes_logic_without_restating",
        "step_3c",
        required=[
            (
                (r"already emits one `Closes #<N>` line per member\s*issue in the "
                r"created PR body"),
                False,
            ),
            (r"does not restate the logic here", False),
        ],
    ),
    Fact(
        "step_3c_documents_solo_path_unchanged",
        "step_3c",
        required=[
            (r"\*\*Solo\*\* — unchanged from today's single-issue invocation", False)
        ],
    ),
    Fact(
        "step_3c_documents_start_iso_capture_for_both_paths",
        "step_3c",
        required=[
            (
                (r"Before invoking `/ship`.*capture the current ISO-8601 timestamp "
                r"as\s*`<start_iso>`"),
                False,
            ),
            (r"3e passes it to the classifier as `--since`", False),
        ],
    ),
    Fact(
        "step_3d_blocked_outcome_applies_to_every_member",
        "step_3d",
        required=[
            (
                r"Label EVERY member issue of the dispatch unit\s*`autoship:blocked`",
                False,
            ),
            (
                r"Post the SAME blocking-question comment to EVERY member issue",
                False,
            ),
            (
                (r'Record outcome `"blocked"` with `blocked_reason: "<questions>"` '
                r"for EVERY\s*member issue"),
                False,
            ),
        ],
    ),
    Fact(
        "step_3d_step5_skips_3d1_and_classifier_but_runs_3e1_and_3f",
        "step_3d",
        required=[
            (
                (r"Skip 3d\.1 and 3e's classifier\*\*\s*\(the outcome is already "
                r"`blocked`\)"),
                False,
            ),
            (r"still run 3e\.1 and 3f for this unit before advancing", False),
        ],
    ),
    Fact(
        "step_3d_block_transition_also_removes_batch_confirmed",
        "step_3d",
        required=[
            (r"remove-label autoship:batch-confirmed", False),
            (
                (r"full replacement label\s*set must also exclude "
                r"`autoship:batch-confirmed`"),
                False,
            ),
        ],
    ),
    Fact(
        "step_3d1_exists_and_applies_to_any_dispatch_unit",
        "step_3d1",
        required=[
            (
                r"### 3d\.1 — Dispatch-unit ship failure/unrecognized handling",
                False,
            ),
            (
                (r"applies to ANY dispatch unit — solo or batch — whose 3e\s*"
                r"classification comes back `failed` or `unrecognized`"),
                False,
            ),
        ],
        forbidden=[(r"applies only to a \*\*batch\*\* dispatch unit", False)],
    ),
    Fact(
        "step_3d1_documents_classifier_ordering_dependency",
        "step_3d1",
        required=[
            (
                (r"Run 3e's classifier first \(below\); return here only if it "
                r"reports\s*`failed` or `unrecognized`"),
                False,
            )
        ],
    ),
    Fact(
        "step_3d1_documents_consistent_label_reversion",
        "step_3d1",
        required=[
            (
                r"Revert every member to a consistent label state together",
                False,
            ),
            (r"never a\s*mix of in-progress/blocked across members", False),
            (r"gh issue edit <n1> <n2> \.\.\. \\", False),
            (r"add-label autoship:blocked", False),
        ],
    ),
    Fact(
        "step_3d1_block_transition_also_removes_batch_confirmed",
        "step_3d1",
        required=[
            (r"remove-label autoship:batch-confirmed", False),
            (
                (r"full replacement label\s*set must also exclude "
                r"`autoship:batch-confirmed`"),
                False,
            ),
        ],
    ),
    Fact(
        "step_3d1_documents_deterministic_batch_level_comment_no_attribution",
        "step_3d1",
        required=[
            (
                (r"no mechanism to identify which specific member issue\s*caused the "
                r"failure"),
                False,
            ),
            (
                (r"always ONE deterministic, batch-level \(or solo\) comment posted "
                r"to every\s*member"),
                False,
            ),
        ],
        forbidden=[
            (r"name that member explicitly", False),
            (
                r"fall back to ONE generic\s*batch-level failure comment",
                False,
            ),
        ],
    ),
    Fact(
        "step_3d1_documents_comment_required_content_and_body_file",
        "step_3d1",
        required=[
            (r"The batch id \(or solo issue number\)", False),
            (r"Every member issue number", False),
            (r"The classifier's verdict word", False),
            (
                r"shared branch/PR link `/ship` produced before failing",
                False,
            ),
            (r"copy-pasteable re-queue command", False),
            (
                (r"gh issue edit <n1> <n2> \.\.\. --remove-label autoship:blocked "
                r"--add-label autoship:ready"),
                False,
            ),
            (r"--body-file", False),
            (r"never inline `--body", False),
        ],
    ),
    Fact(
        "step_3d1_documents_no_idempotency_check_needed",
        "step_3d1",
        required=[
            (
                (r"\*\*No idempotency check is needed here\*\* — unlike Step 2c's\s*"
                r"repeatable proposal comments"),
                False,
            )
        ],
    ),
    Fact(
        "step_3d1_records_failed_or_unrecognized_outcome_for_every_member",
        "step_3d1",
        required=[
            (
                (r"Record outcome `\"failed\"` or `\"unrecognized\"` \(matching 3e's\s*"
                r"classification\) for every member of the dispatch unit"),
                False,
            )
        ],
    ),
    Fact(
        "step_3d1_documents_blocked_reason_populated",
        "step_3d1",
        required=[
            (
                (r"Populate\s*`blocked_reason` with a short synthesized string naming "
                r"the classifier\s*verdict"),
                False,
            ),
            (r"convergence_failure — see comment on issue\(s\)", False),
            (r"never leave it `null` for this outcome", False),
        ],
    ),
    Fact(
        "step_3e_classifies_once_per_dispatch_unit",
        "step_3e",
        required=[
            (r"runs \*\*once per dispatch unit\*\*", False),
            (r"never one classification per member issue", False),
        ],
    ),
    Fact(
        "step_3e1_names_dispatch_unit_generically_like_3a",
        "step_3",
        required=[
            (
                (r"attempted.*next-action.*notes name the dispatch unit the same way\s*"
                r"3a's stop message does"),
                True,
            )
        ],
    ),
    Fact(
        "step_3f_documents_solo_log_shape_unchanged",
        "step_3f",
        required=[
            (r"\*\*Solo\*\* — unchanged, one entry per issue", False),
            (
                r'"round_id":"<round_id>","issue":<number>,"status":"<status>"',
                False,
            ),
        ],
    ),
    Fact(
        "step_3f_documents_batch_log_shape_one_entry_for_all_outcomes",
        "step_3f",
        required=[
            (
                (r"\*\*Batch\*\* — ONE entry per batch, never one entry per member "
                r"issue"),
                False,
            ),
            (
                (r"this\s*shape applies to EVERY outcome alike \(`shipped`, "
                r"`blocked`, and `failed`\)"),
                False,
            ),
            (
                (r'"round_id":"<round_id>","batch_id":"<batch_id>","issues":'
                r'\[<n1>,<n2>,\.\.\.\],"status":"<status>"'),
                False,
            ),
        ],
    ),
    Fact(
        "step_3f_batch_failure_distinguished_from_solo_failed_record",
        "step_3f",
        required=[
            (
                (r'logged as this\s*ONE `"batch_id"` \+ `"issues"` entry with '
                r'`"status":"failed"`'),
                False,
            ),
            (
                (r"structurally\s*distinguishable from a solo entry's single-issue "
                r'`"failed"` record'),
                False,
            ),
            (r"never expanded into three separate failed-solo records", False),
        ],
    ),
    Fact(
        "step_4_summary_table_shows_batch_as_one_row_naming_all_issues",
        "step_4",
        required=[
            (r"\| Issue\(s\)\s*\| Batch ID\s*\| Status\s*\| Notes", False),
            (r"#101, #102, #103\s*\| <batch_id> \| shipped", False),
        ],
    ),
    Fact(
        "step_4_batch_row_documented_for_every_outcome",
        "step_4",
        required=[
            (
                (r"batch dispatch unit occupies exactly ONE row.*regardless of "
                r"outcome\s*\(`shipped`, `blocked`, or `failed` alike\)"),
                False,
            )
        ],
    ),
    Fact(
        "step_4_solo_rows_leave_batch_id_blank",
        "step_4",
        required=[
            (
                (r"solo dispatch unit\*\* occupies one\s*row per issue, same as "
                r"today, with `Batch ID` left blank"),
                True,
            )
        ],
    ),
    Fact(
        "step_4_round_summary_json_splits_processed_and_discovered_units_vs_issues",
        "step_4",
        required=[
            (r'"processed_units":\s*<N>', False),
            (r'"processed_issues":\s*<N>', False),
            (r'"discovered_units":\s*<N>', False),
            (r'"discovered_issues":\s*<N>', False),
        ],
        forbidden=[
            (r'"processed":\s*<N>', False),
            (r'"discovered":\s*<N>', False),
        ],
    ),
    Fact(
        "step_4_documents_units_vs_issues_counting_example",
        "step_4",
        required=[
            (
                (r"ships one 3-issue batch and two solo issues therefore reports\s*"
                r"`processed_units: 3` and `processed_issues: 5`"),
                False,
            )
        ],
    ),
    Fact(
        "step_4_deferred_units_parenthetical_covers_batch_and_solo",
        "step_4",
        required=[
            (
                r"count of dispatch units — batch or solo — left in\s*`deferred`",
                False,
            ),
            (r"a solo unit counts as 1", False),
        ],
        forbidden=[(r"count of dispatch units \(batches\) left in", False)],
    ),
    Fact(
        "step_4_documents_processed_counting_rule_excludes_skipped_units",
        "step_4",
        required=[
            (
                (r"unit counts as\s*`processed` only if Step 3c actually dispatched "
                r"it"),
                False,
            ),
            (
                (r"unit `skip`ped by\s*the cost-cap check \(Step 3a\) is excluded "
                r"from `processed_\*`"),
                False,
            ),
        ],
    ),
    Fact(
        "step_4_documents_discovered_counts_queue_and_deferred_combined",
        "step_4",
        required=[
            (
                (r"`discovered_\*`\s*counts every dispatch unit `autoship_queue\.py` "
                r"produced this round\s*—\s*`queue` and `deferred` combined"),
                False,
            )
        ],
    ),
]


@pytest.mark.parametrize("fact", FACTS, ids=lambda f: f.id)
def test_autoship_skill_doc_fact(skill_text: str, fact: Fact) -> None:
    assert_fact(SECTIONS, skill_text, fact)


# ---------------------------------------------------------------------------
# Facts that don't fit the table: ordering between two positions, a
# substring-count assertion, or (one case) mixing collapsed and raw section
# text for different assertions in the same test.
# ---------------------------------------------------------------------------


def test_step_2_documents_group_script_before_queue_script(skill_text: str) -> None:
    section_text = _step_2(skill_text)
    group_pos = section_text.find("autoship_group.py")
    queue_pos = section_text.find("autoship_queue.py")
    assert group_pos != -1
    assert queue_pos != -1
    assert group_pos < queue_pos


def test_step_2_uses_two_separate_commands_with_a_scratch_file_not_a_pipe(
    skill_text: str,
) -> None:
    # Fix 1: Step 2b/2c need a seam to interpose on — a single shell pipe
    # has none, so the pipeline is now two separate commands connected by
    # an intermediate scratch file.
    section_text = _step_2(skill_text)
    assert not grep(
        r"autoship_group\.py.*\|\s*python3.*autoship_queue\.py",
        collapsed(section_text),
    )
    assert "> <scratch-grouping.json>" in section_text
    assert "--input-file <scratch-grouping.json>" in section_text


def test_step_2_documents_pipe_failure_contract_for_gh_absent_fence_too(
    skill_text: str,
) -> None:
    section_text = collapsed(_step_2(skill_text))
    # Both the gh-present and gh-absent code fences must carry the failure
    # contract — check it appears at least twice (once per fence context).
    assert section_text.count("actionable error is the") >= 2


def test_step_2_quotes_label_and_max_issues_placeholders_in_both_fences(
    skill_text: str,
) -> None:
    section_text = _step_2(skill_text)
    assert grep(r'\[--label "<label>"\]', section_text)
    assert grep(r'--max-issues "<N>"', section_text)
    # Must appear in both the gh-present and gh-absent fences.
    assert section_text.count('[--label "<label>"]') >= 2
    assert section_text.count('--max-issues "<N>"') >= 2


def test_step_2_threads_max_batch_size_into_both_fences(skill_text: str) -> None:
    section_text = _step_2(skill_text)
    assert section_text.count('--max-batch-size "<max_batch_size>"') >= 2


def test_step_2c_exists_immediately_after_step_2b(skill_text: str) -> None:
    section_text = _step_2(skill_text)
    b_pos = section_text.find("### Step 2b")
    c_pos = section_text.find("### Step 2c")
    assert b_pos != -1
    assert c_pos != -1
    assert b_pos < c_pos
