"""Doc-shape contract for plan slice 3 (autoship-issue-batching, Step 3.1):
autoship/SKILL.md's Step 2 must document the two-stage
`autoship_group.py` -> `autoship_queue.py` pipeline instead of the old
single `autoship_discover.py` call.

Plan: plans/autoship-issue-batching.md — Slice 3, Step 3.1.

Also covers Slice 6 (Step 6.1/6.2): Step 3's per-dispatch-unit loop and
Step 4's round summary now consume the `queue` array's `batch`/`solo`
dispatch-unit shape directly — the Slice-3-era "Step 3 still assumes the
old {number, title} shape" gap this file used to assert no longer exists,
by design, as of Slice 6.
"""

from __future__ import annotations

from skill_doc_helpers import (
    PLUGIN_ROOT,
    collapsed,
    frontmatter,
    grep,
    parse_arguments_section,
    section,
)

AUTOSHIP = PLUGIN_ROOT / "skills" / "autoship"
SKILL = AUTOSHIP / "SKILL.md"


def _text() -> str:
    return SKILL.read_text()


def _step_2_section() -> str:
    return section(_text(), r"^## Step 2", boundary_pattern=r"^## Step 3")


# --- 1. Two-stage pipeline documented, in sequence ---------------------------


def test_step_2_documents_group_script_before_queue_script():
    section_text = _step_2_section()
    group_pos = section_text.find("autoship_group.py")
    queue_pos = section_text.find("autoship_queue.py")
    assert group_pos != -1
    assert queue_pos != -1
    assert group_pos < queue_pos


def test_step_2_uses_two_separate_commands_with_a_scratch_file_not_a_pipe():
    # Fix 1: Step 2b/2c need a seam to interpose on — a single shell pipe
    # has none, so the pipeline is now two separate commands connected by
    # an intermediate scratch file.
    section_text = _step_2_section()
    assert not grep(
        r"autoship_group\.py.*\|\s*python3.*autoship_queue\.py",
        collapsed(section_text),
    )
    assert "> <scratch-grouping.json>" in section_text
    assert "--input-file <scratch-grouping.json>" in section_text


# --- 2. Old single autoship_discover.py call absent from Step 2 -------------


def test_step_2_no_longer_documents_single_discover_call_feeding_loop():
    # autoship_discover.py may still be named elsewhere in this section (the
    # "not part of this pipeline" note) — scope this negative assertion to
    # the specific old invocation shape, not a bare mention of the script.
    section_text = _step_2_section()
    assert not grep(r"autoship_discover\.py \\\s*\n\s*--max-issues", section_text)


def test_step_2_names_discover_script_as_no_longer_part_of_pipeline():
    section_text = collapsed(_step_2_section())
    assert grep(r"autoship_discover\.py.*not.*part of this pipeline", section_text)
    assert grep(r"do not modify or remove that script", section_text)


# --- 3. autoship_group.py self-fetches full pool, no --max-issues cap -------


def test_step_2_documents_group_script_fetches_full_pool_without_max_issues_cap():
    section_text = collapsed(_step_2_section())
    assert grep(r"self-fetches the \*\*full\*\* eligible pool", section_text)
    assert grep(r"no `--max-issues` truncation at that layer", section_text)


# --- 4. --label now flows to autoship_group.py ------------------------------


def test_step_2_documents_label_flag_flows_to_group_script():
    section_text = collapsed(_step_2_section())
    assert grep(
        r"flows to `autoship_group\.py --label\s*<label>` instead of "
        r"`autoship_discover\.py --label <label>`",
        section_text,
    )


# --- 5. Empty-queue stop condition -------------------------------------------


def test_step_2_documents_empty_queue_stop_message():
    section_text = collapsed(_step_2_section())
    assert grep(r"both `queue` and `deferred` empty", section_text)
    assert grep(r"No eligible issues found this round\.", section_text)


# --- 6. --dry-run behavior against the new queue shape ----------------------


def test_step_2_documents_dry_run_prints_queue_and_stops():
    section_text = collapsed(_step_2_section())
    assert grep(
        r"--dry-run.*mode, print the discovered queue and stop here", section_text
    )


def test_step_2_dry_run_stop_line_uses_per_dispatch_unit_wording():
    # Fix K: stale "per-issue processing" predates the batch rewrite.
    section_text = collapsed(_step_2_section())
    assert grep(
        r"stop here without\s*proceeding to per-dispatch-unit processing",
        section_text,
    )
    assert not grep(r"per-issue processing", section_text)


def test_role_description_uses_per_dispatch_unit_not_per_issue():
    # Fix K: the Role/description section near the top of the file predates
    # the batch rewrite too.
    text = _text()
    assert "pipeline per dispatch unit and logs each outcome" in text
    assert "pipeline per issue and logs each outcome" not in text


# --- 7. Step 3 now processes the queue directly (Slice 6 supersedes the ---
# --- Slice-3-era transition-gap disclaimer) ----------------------------------


def test_step_2_no_longer_names_a_step_3_transition_gap():
    # Slice 6 wired Step 3 to consume the queue's batch/solo dispatch units,
    # so the Slice-3-era disclaimer that Step 3 "has not yet been updated"
    # must not survive into this doc.
    section_text = collapsed(_step_2_section())
    assert not grep(
        r"Step 3's prose below is still written for the old "
        r"`\{number, title\}` shape",
        section_text,
    )
    assert grep(
        r"Step 3 processes this\s*queue directly, one dispatch unit at a "
        r"time, in order",
        section_text,
    )


# --- 8. Fix 1: empty-queue-with-deferred branch, and deferred count -------


def test_step_2_documents_empty_queue_nonempty_deferred_branch():
    section_text = collapsed(_step_2_section())
    assert grep(r"`queue` is empty but `deferred` is \*\*not\*\* empty", section_text)
    assert grep(r"No dispatchable unit fits --max-issues <N> this round", section_text)
    assert grep(r"unit\(s\) deferred\s*whole", section_text)
    assert grep(
        r"do not.*silently fall through to Step 3", section_text, ignore_case=True
    )


def _step_4_section():
    return section(_text(), r"^## Step 4", boundary_pattern=r"^## Notes")


def test_step_4_round_summary_includes_deferred_count():
    section_text = collapsed(_step_4_section())
    assert grep(r"Deferred\s*:\s*<N> unit\(s\), <M> issue\(s\)", section_text)


def test_step_4_round_summary_json_distinguishes_units_from_issues():
    section_text = collapsed(_step_4_section())
    assert grep(r'"deferred_units":\s*<N>', section_text)
    assert grep(r'"deferred_issues":\s*<M>', section_text)
    assert not grep(r'"deferred":\s*<N>', section_text)


def test_step_4_status_enum_covers_both_early_exit_stops():
    section_text = collapsed(_step_4_section())
    assert grep(r'"no_eligible_issues"', section_text)
    assert grep(r'"no_unit_fits_cap"', section_text)


def test_step_2_early_exits_record_the_new_status_values():
    section_text = collapsed(_step_2_section())
    assert grep(r'status:\s*"no_eligible_issues"', section_text)
    assert grep(r'status:\s*"no_unit_fits_cap"', section_text)


# --- 9. Fix 2: pipe-failure contract documented for both fences -----------


def test_step_2_documents_discovery_pipe_failure_is_fatal():
    section_text = collapsed(_step_2_section())
    assert grep(r"a discovery failure is fatal for the round", section_text)
    assert grep(
        r"the actionable error is the `autoship_group:`-prefixed",
        section_text,
    )
    assert grep(r"autoship_queue\.py.*will report its own unrelated", section_text)


def test_step_2_documents_pipe_failure_contract_for_gh_absent_fence_too():
    section_text = collapsed(_step_2_section())
    # Both the gh-present and gh-absent code fences must carry the failure
    # contract — check it appears at least twice (once per fence context).
    assert section_text.count("actionable error is the") >= 2


# --- 10. Fix 3: quoted placeholders in both Step 2 code fences ------------


def test_step_2_quotes_label_and_max_issues_placeholders_in_both_fences():
    section_text = _step_2_section()
    assert grep(r'\[--label "<label>"\]', section_text)
    assert grep(r'--max-issues "<N>"', section_text)
    # Must appear in both the gh-present and gh-absent fences.
    assert section_text.count('[--label "<label>"]') >= 2
    assert section_text.count('--max-issues "<N>"') >= 2


# --- 11. Step 3 processes the queue's dispatch units directly (Slice 6) ----


def _step_3_section():
    return section(_text(), r"^## Step 3", boundary_pattern=r"^## Step 4")


def test_step_3_no_longer_opens_with_the_shape_mismatch_disclaimer():
    section_text = collapsed(_step_3_section())
    assert not grep(
        r"this step's prose still assumes the old `\{number, title\}` "
        r"per-issue shape",
        section_text,
    )


def test_step_3_processes_queue_array_dispatch_units_directly():
    section_text = collapsed(_step_3_section())
    assert grep(
        r"each a \*\*dispatch unit\*\*, either\s*"
        r'`\{"type": "batch", "batch_id": \.\.\., "issues": \[n1, n2, \.\.\.\]\}`',
        section_text,
    )
    assert grep(r'`\{"type": "solo", "issue": N\}`', section_text)
    assert grep(r"strictly in order", section_text, ignore_case=True)


# --- 12. Fix 5: Step 1's reclaim rationale is corrected --------------------


def _step_1_section():
    return section(_text(), r"^## Step 1", boundary_pattern=r"^## Step 2")


def test_step_1_no_longer_claims_reclaim_affects_max_issues_accounting():
    section_text = collapsed(_step_1_section())
    assert not grep(r"so they are not counted against", section_text)


def test_step_1_states_corrected_reclaim_rationale():
    section_text = collapsed(_step_1_section())
    assert grep(r"does not change `--max-issues`\s*accounting", section_text)
    assert grep(r"autoship_state\.is_eligible", section_text)
    assert grep(
        r"real purpose is unsticking issues orphaned by a crashed round",
        section_text,
    )


# --- 13. Fix 6: --max-batch-size reachable from /autoship ------------------


def test_parse_arguments_documents_max_batch_size_flag():
    section_text = collapsed(parse_arguments_section(_text()))
    assert grep(r"--max-batch-size N", section_text)


def test_usage_string_agrees_with_argument_hint_on_max_batch_size():
    section_text = collapsed(parse_arguments_section(_text()))
    assert grep(r"Usage: /autoship.*--max-batch-size N", section_text)
    assert grep(r"default:\s*5", section_text)


def test_frontmatter_argument_hint_includes_max_batch_size():
    fm = frontmatter(_text())
    assert grep(r"\[--max-batch-size N\]", fm)


def test_step_2_threads_max_batch_size_into_both_fences():
    section_text = _step_2_section()
    assert section_text.count('--max-batch-size "<max_batch_size>"') >= 2


# --- Slice 4, Step 4.1: leftover grouping (one agent dispatch per round) -----


def _step_2b_section():
    return section(_text(), r"^### Step 2b", boundary_pattern=r"^### Step 2c")


def test_step_2b_exists_after_step_2_pipeline():
    section_text = _step_2_section()
    assert "### Step 2b" in section_text


def test_step_2b_documents_one_agent_dispatch_per_round_not_per_issue():
    section_text = collapsed(_step_2b_section())
    assert grep(r"dispatch \*\*exactly one agent\*\* for this round", section_text)
    assert grep(r"never one agent dispatch per ungrouped issue", section_text)


def test_step_2b_documents_zero_ungrouped_no_op_case():
    section_text = collapsed(_step_2b_section())
    assert grep(
        r"Fewer than two ungrouped issues.*skip this stage entirely", section_text
    )
    assert grep(r"No agent is dispatched\s*this round at all", section_text)


def test_step_2b_documents_two_or_more_threshold_for_dispatch():
    # Fix 8: the dispatch threshold changed from "one or more" to "two or
    # more" — a single leftover issue can't be grouped with anything.
    section_text = collapsed(_step_2b_section())
    assert grep(r"\*\*Two or more ungrouped issues\*\*: dispatch", section_text)
    assert grep(r"\(zero, or exactly one\)", section_text)


def test_step_2b_documents_oversized_proposal_trim_rule():
    section_text = collapsed(_step_2b_section())
    assert grep(
        r"to its oldest `--max-batch-size` members by the SAME rule",
        section_text,
        ignore_case=True,
    )
    assert grep(r"oldest-first", section_text)
    assert grep(
        r"overflow returns to ungrouped rather than being dropped", section_text
    )


def test_step_2b_documents_untaken_issues_proceed_as_solo():
    section_text = collapsed(_step_2b_section())
    assert grep(
        r"remain ungrouped and proceed to `autoship_queue\.py` as solo "
        r"dispatch\s*units, exactly as today",
        section_text,
    )


# --- Slice 4, Step 4.2: block-and-comment confirm/reject contract -----------


def _step_2c_section():
    return section(_text(), r"^### Step 2c", boundary_pattern=r"^## Step 3")


def test_step_2c_exists_immediately_after_step_2b():
    section_text = _step_2_section()
    b_pos = section_text.find("### Step 2b")
    c_pos = section_text.find("### Step 2c")
    assert b_pos != -1
    assert c_pos != -1
    assert b_pos < c_pos


def test_step_2c_documents_block_applies_blocked_and_removes_ready():
    section_text = collapsed(_step_2c_section())
    assert grep(
        r"label EVERY member issue `autoship:blocked`, removing\s*"
        r"`autoship:ready` in the same operation",
        section_text,
    )


def test_step_2c_documents_comment_required_content():
    section_text = collapsed(_step_2c_section())
    assert grep(r"The grouping rationale", section_text)
    assert grep(r"Every member issue number in the proposed batch", section_text)
    assert grep(
        r"gh issue edit <n1> <n2> \.\.\. --add-label autoship:batch-confirmed "
        r"--remove-label autoship:blocked --add-label autoship:ready",
        section_text,
    )


def test_step_2c_documents_confirm_outcome_partial_supported():
    section_text = collapsed(_step_2c_section())
    assert grep(
        r"partial confirmation is explicitly supported, not an error",
        section_text,
    )
    assert grep(
        r"Whichever subset of the ORIGINAL proposal ends up carrying\s*"
        r"`autoship:batch-confirmed` is what the NEXT round's deterministic "
        r"grouping\s*pass groups",
        section_text,
        ignore_case=True,
    )


def test_step_2c_documents_reject_outcome_returns_to_solo_eligibility():
    section_text = collapsed(_step_2c_section())
    assert grep(
        r"WITHOUT\s*adding `autoship:batch-confirmed`",
        section_text,
        ignore_case=True,
    )
    assert grep(
        r"returns to plain solo eligibility next round and is NOT "
        r"re-proposed as part\s*of the same batch",
        section_text,
        ignore_case=True,
    )


def test_step_2c_documents_label_transition_atomicity_rule():
    section_text = collapsed(_step_2c_section())
    assert grep(
        r"applying `autoship:blocked` always removes\s*`autoship:ready` in "
        r"the same operation",
        section_text,
    )
    assert grep(
        r"applying\s*`autoship:batch-confirmed` \+ `autoship:ready` always "
        r"removes\s*`autoship:blocked` in the same operation",
        section_text,
    )


def test_step_2c_documents_batch_confirmed_and_ready_coexist():
    section_text = collapsed(_step_2c_section())
    assert grep(
        r"`autoship:batch-confirmed`\s*and `autoship:ready` DO co-occur "
        r"together once a batch is confirmed",
        section_text,
        ignore_case=True,
    )


def test_step_2c_documents_blocked_mutual_exclusivity_clause():
    # Fix 8: assert the mutual-exclusivity clause itself, not just the
    # co-occurrence clause covered by the test above.
    section_text = collapsed(_step_2c_section())
    assert grep(
        r"never co-present with\s*`autoship:ready` or with "
        r"`autoship:batch-confirmed`",
        section_text,
    )


# --- Fix 1: two-command pipeline with a scratch file, failure contract -----


def test_step_2_documents_confirmed_batch_members_resolution_note():
    section_text = collapsed(_step_2_section())
    assert grep(r"Resolving `confirmed_batch_members`", section_text)
    assert grep(r"gh issue view <n> --json comments", section_text)


def test_step_2_documents_gh_absent_confirmed_batch_members_known_gap():
    section_text = collapsed(_step_2_section())
    assert grep(r"Known gap, gh-absent `confirmed_batch_members` only", section_text)
    assert grep(r"no call that returns an issue's comment bodies", section_text)


# --- Fix 2: proposed-batch members removed from the ungrouped array --------


def test_step_2c_documents_removing_batch_members_from_ungrouped_array():
    section_text = collapsed(_step_2c_section())
    assert grep(
        r"delete every member of every proposed batch \*\*that was actually\s*"
        r"BLOCKED above\*\*\s*from\s*`<scratch-grouping\.json>`'s `ungrouped` array",
        section_text,
    )
    assert grep(r"must not be dispatched solo or in any batch this round", section_text)


# --- Fix 3: hidden marker, idempotency, signal function, gh-present fetch --


def test_step_2c_documents_hidden_batch_members_marker():
    section_text = collapsed(_step_2c_section())
    assert grep(r"<!-- autoship-batch-members: <n1>,<n2>,\.\.\. -->", section_text)


def test_step_2c_documents_marker_idempotency_check():
    section_text = collapsed(_step_2c_section())
    assert grep(r"\*\*Idempotency\*\*", section_text)
    assert grep(r"skip posting", section_text)
    assert grep(r"never re-post an equivalent proposal comment", section_text)


def test_step_2c_confirm_outcome_names_the_actual_mechanism():
    # Fix 3: the "Confirm outcome" paragraph must name the marker mechanism
    # and the signal function that makes the claim true.
    section_text = collapsed(_step_2c_section())
    assert grep(r"has_batch_confirmed_override", section_text)
    assert grep(r"confirmed_batch_members.*marker", section_text)


# --- Fix 4: dry-run guard on Step 2b and Step 2c ----------------------------


def test_step_2b_documents_dry_run_guard():
    section_text = collapsed(_step_2b_section())
    assert grep(r"\*\*Dry-run guard\.\*\*", section_text)
    assert grep(r"skip the agent dispatch entirely", section_text)


def test_step_2c_documents_dry_run_guard():
    section_text = collapsed(_step_2c_section())
    assert grep(r"\*\*Dry-run guard\.\*\*", section_text)
    assert grep(r"skip every mutation below", section_text)


# --- Fix 5: named agent, Task tool, schema, response validation -------------


def test_step_2b_names_general_purpose_agent_dispatched_via_task_tool():
    section_text = collapsed(_step_2b_section())
    assert grep(r"via the `Task`\s*tool, subagent type `general-purpose`", section_text)


def test_frontmatter_allowed_tools_includes_task():
    fm = frontmatter(_text())
    assert grep(r"\bTask\b", fm)


def test_step_2b_documents_agent_output_json_schema():
    section_text = _step_2b_section()
    assert '{"proposals": [{"rationale": "...", "issues": [101, 102]}]}' in section_text


def test_step_2b_documents_response_validation_rules():
    section_text = collapsed(_step_2b_section())
    assert grep(r"not present in the current\s*`ungrouped` set", section_text)
    assert grep(r"appears in more than one proposal", section_text)
    assert grep(r"keeping only\s*its FIRST occurrence", section_text, ignore_case=True)
    assert grep(r"fewer than 2 members after steps 1-3", section_text)
    assert grep(r"treat it as zero proposals", section_text)


# --- Fix 6: cost-cap check before Step 2b dispatch --------------------------


def test_step_2b_documents_cost_cap_check_before_dispatch():
    section_text = collapsed(_step_2b_section())
    assert grep(r"\*\*Cost-cap check \(before dispatch\)\.\*\*", section_text)
    assert grep(r"/cost-report", section_text)
    assert grep(r"skip the agent dispatch entirely", section_text)
    assert grep(r"counts against `--max-cost-usd` like everything else", section_text)


# --- Fix 7: command/argument injection guards -------------------------------


def test_step_2c_documents_issue_number_validation():
    section_text = collapsed(_step_2c_section())
    assert r"^[0-9]+$" in section_text
    assert grep(r"rejected in\s*its entirety", section_text)


def test_step_2c_documents_body_file_usage_not_inline_body():
    section_text = collapsed(_step_2c_section())
    assert grep(r"--body-file", section_text)
    assert grep(r"never inline `--body", section_text)
    assert "--body-file <scratch-comment-file>" in section_text


# --- Fix 8: gh-absent mechanisms for Step 2c's Block and Comment -----------


def test_step_2c_documents_gh_absent_block_mechanism():
    section_text = collapsed(_step_2c_section())
    assert grep(
        r"mcp__github__issue_write.*method `update`.*per member issue", section_text
    )


def test_step_2c_documents_gh_absent_comment_mechanism():
    section_text = collapsed(_step_2c_section())
    assert grep(
        r"mcp__github__add_issue_comment.*with the same composed body", section_text
    )


# --- Closing-pass review fixes -----------------------------------------------


# Fix A: security-rejected batches must not silently vanish from ungrouped.


def test_step_2c_scopes_removal_to_batches_actually_blocked():
    section_text = collapsed(_step_2c_section())
    assert grep(
        r"delete every member of every proposed batch \*\*that was actually\s*"
        r"BLOCKED above\*\*",
        section_text,
    )
    assert grep(r"was never blocked", section_text)
    assert grep(
        r"its members MUST stay in `ungrouped` and\s*proceed to "
        r"`autoship_queue\.py` as solo dispatch units",
        section_text,
    )


# Fix B: Step 2b must document how to fetch each ungrouped issue's body.


def test_step_2b_documents_body_resolution_dual_path():
    section_text = collapsed(_step_2b_section())
    assert grep(r"Resolving each issue's body \(before dispatch\)", section_text)
    assert grep(r"gh issue view <n> --json title,body", section_text)
    assert grep(
        r"mcp__github__issue_read.*\(method `get`, that issue\s*number\) per "
        r"currently-\s*ungrouped issue",
        section_text,
    )


# Fix C: Idempotency check must be dual-pathed (gh-present vs gh-absent).


def test_step_2c_documents_idempotency_check_dual_path():
    section_text = collapsed(_step_2c_section())
    assert grep(r"gh issue view <n> --json comments.*per member issue", section_text)
    assert grep(
        r"this skill's MCP toolset has no call that returns an issue's\s*"
        r"comment bodies",
        section_text,
    )
    assert grep(r"Post the proposal\s*comment unconditionally", section_text)
    assert grep(
        r"a duplicate proposal comment is the accepted\s*degradation in this mode",
        section_text,
    )


# Fix D: validation enumeration broadened to name every command/value site.


def test_step_2c_validation_enumeration_names_all_injection_sites():
    section_text = collapsed(_step_2c_section())
    assert grep(
        r"the `gh issue comment <n1> --body-file \.\.\.`\s*invocation itself",
        section_text,
    )
    assert grep(
        r"the `<!-- autoship-batch-members: \.\.\. -->` marker values",
        section_text,
    )
    assert grep(r"the `<scratch-grouping\.json>` ungrouped-array rewrite", section_text)


def test_step_2c_marker_item_carries_already_validated_qualifier():
    section_text = collapsed(_step_2c_section())
    assert grep(
        r"member list \(already validated above\), appended after", section_text
    )


# Fix E: marker readback must validate author identity and value shape.


def test_step_2_documents_marker_author_validation():
    section_text = collapsed(_step_2_section())
    assert grep(
        r"only extract it from a comment posted by this\s*skill's own actor",
        section_text,
    )
    assert grep(
        r"filter `comments\[\]\.author\.login` against the\s*invoking bot/user identity",
        section_text,
    )


def test_step_2_documents_marker_value_validation():
    section_text = collapsed(_step_2_section())
    assert grep(
        r"validate every parsed value matches `\^\[0-9\]\+\$` before merging it\s*"
        r"into `confirmed_batch_members`",
        section_text,
    )
    assert grep(r"drop the whole marker", section_text)


# Fix G: documented, accepted concurrency caveat on the idempotency guard.


def test_step_2c_documents_concurrency_caveat():
    section_text = collapsed(_step_2c_section())
    assert grep(r"not atomic\s*across concurrent `/autoship` invocations", section_text)
    assert grep(
        r"two overlapping rounds could\s*both pass the check before either posts",
        section_text,
    )
    assert grep(r"accepted limitation", section_text)
    assert grep(r"existing \"Sequential\s*only\" constraint", section_text)


# --- Slice 6, Step 6.1: batch dispatch via /ship --issues, outcome ----------
# --- propagated to every member ---------------------------------------------


def _step_3b_section():
    return section(_step_3_section(), r"^### 3b", boundary_pattern=r"^### 3c")


def _step_3c_section():
    return section(_step_3_section(), r"^### 3c", boundary_pattern=r"^### 3d")


def _step_3d_section():
    return section(_step_3_section(), r"^### 3d ", boundary_pattern=r"^### 3d\.1")


def _step_3d1_section():
    return section(_step_3_section(), r"^### 3d\.1", boundary_pattern=r"^### 3e ")


def _step_3e_section():
    return section(_step_3_section(), r"^### 3e ", boundary_pattern=r"^### 3e\.1")


def _step_3f_section():
    return section(_step_3_section(), r"^### 3f", boundary_pattern=r"^## Step 4")


def test_step_3a_stop_message_names_dispatch_unit_generically():
    section_text = collapsed(_step_3_section())
    assert grep(r"Stopping before <unit>", section_text)
    assert grep(
        r"`<unit>` names the dispatch unit generically.*`issue #<number>` "
        r"for a solo\s*unit, or `batch <batch_id> \(issues #<n1>, #<n2>, "
        r"\.\.\.\)` for a batch unit",
        section_text,
    )


def test_step_3b_documents_batch_multi_issue_label_in_progress():
    section_text = collapsed(_step_3b_section())
    assert grep(
        r"label EVERY member issue `autoship:in-progress` together, in one\s*"
        r"operation",
        section_text,
    )
    assert grep(r"gh issue edit <n1> <n2> \.\.\. \\", section_text)
    assert grep(r"add-label autoship:in-progress", section_text)


def test_step_3b_documents_solo_path_unchanged():
    section_text = collapsed(_step_3b_section())
    assert grep(
        r"\*\*Solo\*\* — unchanged from today's single-issue behavior", section_text
    )


def test_step_3c_documents_batch_invokes_ship_once_with_issues_flag():
    section_text = collapsed(_step_3c_section())
    assert grep(
        r"invoke `/ship` \*\*once\*\*, with `--issues <n1>,<n2>,\.\.\.` naming\s*"
        r"every member issue",
        section_text,
    )
    assert grep(r"--issues <n1>,<n2>,\.\.\. --no-auto-merge", section_text)


def test_step_3c_batch_cites_ship_closes_logic_without_restating():
    section_text = collapsed(_step_3c_section())
    assert grep(
        r"already emits one `Closes #<N>` line per member\s*issue in the "
        r"created PR body",
        section_text,
    )
    assert grep(r"does not restate the logic here", section_text)


def test_step_3c_documents_solo_path_unchanged():
    section_text = collapsed(_step_3c_section())
    assert grep(
        r"\*\*Solo\*\* — unchanged from today's single-issue invocation",
        section_text,
    )


def test_step_3c_documents_start_iso_capture_for_both_paths():
    # Fix C: 3e says it uses the start ISO timestamp "captured just before
    # invoking /ship in Step 3c" — but 3c never actually said to capture it.
    section_text = collapsed(_step_3c_section())
    assert grep(
        r"Before invoking `/ship`.*capture the current ISO-8601 timestamp "
        r"as\s*`<start_iso>`",
        section_text,
    )
    assert grep(r"3e passes it to the classifier as `--since`", section_text)


def test_step_3d_blocked_outcome_applies_to_every_member():
    section_text = collapsed(_step_3d_section())
    assert grep(
        r"Label EVERY member issue of the dispatch unit\s*`autoship:blocked`",
        section_text,
    )
    assert grep(
        r"Post the SAME blocking-question comment to EVERY member issue",
        section_text,
    )
    assert grep(
        r'Record outcome `"blocked"` with `blocked_reason: "<questions>"` '
        r"for EVERY\s*member issue",
        section_text,
    )


def test_step_3d_step5_skips_3d1_and_classifier_but_runs_3e1_and_3f():
    # Fix A: 3d's step 5 used to route straight past 3e.1 (the hard-block
    # journal gate) and 3f (the log-append step), both of which explicitly
    # handle the "blocked" outcome.
    section_text = collapsed(_step_3d_section())
    assert grep(
        r"Skip 3d\.1 and 3e's classifier\*\*\s*\(the outcome is already "
        r"`blocked`\)",
        section_text,
    )
    assert grep(
        r"still run 3e\.1 and 3f for this unit before advancing",
        section_text,
    )


def test_step_3d_block_transition_also_removes_batch_confirmed():
    # Fix B: blocking a batch formed via the batch-confirmed override must
    # also strip autoship:batch-confirmed, or the "mutually exclusive"
    # invariant this file states elsewhere is violated.
    section_text = collapsed(_step_3d_section())
    assert grep(r"remove-label autoship:batch-confirmed", section_text)
    assert grep(
        r"full replacement label\s*set must also exclude "
        r"`autoship:batch-confirmed`",
        section_text,
    )


# --- New: dispatch-unit ship failure/unrecognized handling (3d.1) -----------


def test_step_3d1_exists_and_applies_to_any_dispatch_unit():
    # Fix H: the batch-only restriction is gone — 3d.1 now applies to any
    # dispatch unit (solo or batch) whose 3e classification is failed or
    # unrecognized.
    section_text = collapsed(_step_3d1_section())
    assert grep(
        r"### 3d\.1 — Dispatch-unit ship failure/unrecognized handling",
        section_text,
    )
    assert grep(
        r"applies to ANY dispatch unit — solo or batch — whose 3e\s*"
        r"classification comes back `failed` or `unrecognized`",
        section_text,
    )
    assert not grep(r"applies only to a \*\*batch\*\* dispatch unit", section_text)


def test_step_3d1_documents_classifier_ordering_dependency():
    # Fix D: 3d.1 sits before 3e in document order, so the dependency on 3e
    # running first must be stated explicitly.
    section_text = collapsed(_step_3d1_section())
    assert grep(
        r"Run 3e's classifier first \(below\); return here only if it "
        r"reports\s*`failed` or `unrecognized`",
        section_text,
    )


def test_step_3d1_documents_consistent_label_reversion():
    section_text = collapsed(_step_3d1_section())
    assert grep(
        r"Revert every member to a consistent label state together", section_text
    )
    assert grep(r"never a\s*mix of in-progress/blocked across members", section_text)
    assert grep(r"gh issue edit <n1> <n2> \.\.\. \\", section_text)
    assert grep(r"add-label autoship:blocked", section_text)


def test_step_3d1_block_transition_also_removes_batch_confirmed():
    # Fix B: the block relabel must also strip autoship:batch-confirmed —
    # otherwise a batch formed via the batch-confirmed override keeps that
    # label after being blocked, violating the mutual-exclusivity invariant.
    section_text = collapsed(_step_3d1_section())
    assert grep(r"remove-label autoship:batch-confirmed", section_text)
    assert grep(
        r"full replacement label\s*set must also exclude "
        r"`autoship:batch-confirmed`",
        section_text,
    )


def test_step_3d1_documents_deterministic_batch_level_comment_no_attribution():
    # Fix G: the pipeline has no per-issue attribution signal — the comment
    # is always one deterministic, batch-level (or solo) comment, never a
    # named-cause-for-one-member variant.
    section_text = collapsed(_step_3d1_section())
    assert grep(
        r"no mechanism to identify which specific member issue\s*caused the "
        r"failure",
        section_text,
    )
    assert grep(
        r"always ONE deterministic, batch-level \(or solo\) comment posted "
        r"to every\s*member",
        section_text,
    )
    assert not grep(r"name that member explicitly", section_text)
    assert not grep(
        r"fall back to ONE generic\s*batch-level failure comment", section_text
    )


def test_step_3d1_documents_comment_required_content_and_body_file():
    # Fix I: REQUIRED-content list + --body-file convention, mirroring 2c's
    # comment shape.
    section_text = collapsed(_step_3d1_section())
    assert grep(r"The batch id \(or solo issue number\)", section_text)
    assert grep(r"Every member issue number", section_text)
    assert grep(r"The classifier's verdict word", section_text)
    assert grep(r"shared branch/PR link `/ship` produced before failing", section_text)
    assert grep(r"copy-pasteable re-queue command", section_text)
    assert grep(
        r"gh issue edit <n1> <n2> \.\.\. --remove-label autoship:blocked "
        r"--add-label autoship:ready",
        section_text,
    )
    assert grep(r"--body-file", section_text)
    assert grep(r"never inline `--body", section_text)


def test_step_3d1_documents_no_idempotency_check_needed():
    # Fix I: unlike 2c's repeatable proposal comments, this fires once per
    # dispatch unit per round terminal outcome — state that explicitly.
    section_text = collapsed(_step_3d1_section())
    assert grep(
        r"\*\*No idempotency check is needed here\*\* — unlike Step 2c's\s*"
        r"repeatable proposal comments",
        section_text,
    )


def test_step_3d1_records_failed_or_unrecognized_outcome_for_every_member():
    section_text = collapsed(_step_3d1_section())
    assert grep(
        r"Record outcome `\"failed\"` or `\"unrecognized\"` \(matching 3e's\s*"
        r"classification\) for every member of the dispatch unit",
        section_text,
    )


def test_step_3d1_documents_blocked_reason_populated():
    # Fix J: unlike a blocked entry's extracted question, 3d.1's failed/
    # unrecognized entry had no reason field at all — now it does.
    section_text = collapsed(_step_3d1_section())
    assert grep(
        r"Populate\s*`blocked_reason` with a short synthesized string naming "
        r"the classifier\s*verdict",
        section_text,
    )
    assert grep(r"convergence_failure — see comment on issue\(s\)", section_text)
    assert grep(r"never leave it `null` for this outcome", section_text)


def test_step_3e_classifies_once_per_dispatch_unit():
    section_text = collapsed(_step_3e_section())
    assert grep(r"runs \*\*once per dispatch unit\*\*", section_text)
    assert grep(
        r"never one classification per member issue",
        section_text,
    )


def test_step_3e1_names_dispatch_unit_generically_like_3a():
    section_text = collapsed(_step_3_section())
    assert grep(
        r"attempted.*next-action.*notes name the dispatch unit the same way\s*"
        r"3a's stop message does",
        section_text,
        ignore_case=True,
    )


def test_step_3f_documents_solo_log_shape_unchanged():
    section_text = collapsed(_step_3f_section())
    assert grep(r"\*\*Solo\*\* — unchanged, one entry per issue", section_text)
    assert grep(
        r'"round_id":"<round_id>","issue":<number>,"status":"<status>"',
        section_text,
    )


def test_step_3f_documents_batch_log_shape_one_entry_for_all_outcomes():
    section_text = collapsed(_step_3f_section())
    assert grep(
        r"\*\*Batch\*\* — ONE entry per batch, never one entry per member "
        r"issue",
        section_text,
    )
    assert grep(
        r"this\s*shape applies to EVERY outcome alike \(`shipped`, "
        r"`blocked`, and `failed`\)",
        section_text,
    )
    assert grep(
        r'"round_id":"<round_id>","batch_id":"<batch_id>","issues":'
        r'\[<n1>,<n2>,\.\.\.\],"status":"<status>"',
        section_text,
    )


def test_step_3f_batch_failure_distinguished_from_solo_failed_record():
    section_text = collapsed(_step_3f_section())
    assert grep(
        r'logged as this\s*ONE `"batch_id"` \+ `"issues"` entry with '
        r'`"status":"failed"`',
        section_text,
    )
    assert grep(
        r"structurally\s*distinguishable from a solo entry's single-issue "
        r'`"failed"` record',
        section_text,
    )
    assert grep(r"never expanded into three separate failed-solo records", section_text)


# --- Slice 6, Step 6.2: round summary distinguishes batch vs solo entries --


def test_step_4_summary_table_shows_batch_as_one_row_naming_all_issues():
    section_text = collapsed(_step_4_section())
    assert grep(r"\| Issue\(s\)\s*\| Batch ID\s*\| Status\s*\| Notes", section_text)
    assert grep(r"#101, #102, #103\s*\| <batch_id> \| shipped", section_text)


def test_step_4_batch_row_documented_for_every_outcome():
    section_text = collapsed(_step_4_section())
    assert grep(
        r"batch dispatch unit occupies exactly ONE row.*regardless of "
        r"outcome\s*\(`shipped`, `blocked`, or `failed` alike\)",
        section_text,
    )


def test_step_4_solo_rows_leave_batch_id_blank():
    section_text = collapsed(_step_4_section())
    assert grep(
        r"solo dispatch unit\*\* occupies one\s*row per issue, same as "
        r"today, with `Batch ID` left blank",
        section_text,
        ignore_case=True,
    )


def test_step_4_round_summary_json_splits_processed_and_discovered_units_vs_issues():
    section_text = collapsed(_step_4_section())
    assert grep(r'"processed_units":\s*<N>', section_text)
    assert grep(r'"processed_issues":\s*<N>', section_text)
    assert grep(r'"discovered_units":\s*<N>', section_text)
    assert grep(r'"discovered_issues":\s*<N>', section_text)
    assert not grep(r'"processed":\s*<N>', section_text)
    assert not grep(r'"discovered":\s*<N>', section_text)


def test_step_4_documents_units_vs_issues_counting_example():
    section_text = collapsed(_step_4_section())
    assert grep(
        r"ships one 3-issue batch and two solo issues therefore reports\s*"
        r"`processed_units: 3` and `processed_issues: 5`",
        section_text,
    )


def test_step_4_deferred_units_parenthetical_covers_batch_and_solo():
    # Fix E: autoship_queue.py's build_queue defers any unit type that
    # doesn't fit the cap, solo included — not just batches.
    section_text = collapsed(_step_4_section())
    assert grep(
        r"count of dispatch units — batch or solo — left in\s*`deferred`",
        section_text,
    )
    assert grep(r"a solo unit counts as 1", section_text)
    assert not grep(r"count of dispatch units \(batches\) left in", section_text)


def test_step_4_documents_processed_counting_rule_excludes_skipped_units():
    # Fix F: a unit skipped by the cost-cap check never dispatched, so it
    # must not count toward processed_*.
    section_text = collapsed(_step_4_section())
    assert grep(
        r"unit counts as\s*`processed` only if Step 3c actually dispatched "
        r"it",
        section_text,
    )
    assert grep(
        r"unit `skip`ped by\s*the cost-cap check \(Step 3a\) is excluded "
        r"from `processed_\*`",
        section_text,
    )


def test_step_4_documents_discovered_counts_queue_and_deferred_combined():
    # Fix F: discovered_* counts every unit autoship_queue.py produced this
    # round, queue and deferred combined.
    section_text = collapsed(_step_4_section())
    assert grep(
        r"`discovered_\*`\s*counts every dispatch unit `autoship_queue\.py` "
        r"produced this round\s*—\s*`queue` and `deferred` combined",
        section_text,
    )
