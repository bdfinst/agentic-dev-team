"""Doc-shape contract for plan slice 3 (autoship-issue-batching, Step 3.1):
autoship/SKILL.md's Step 2 must document the two-stage
`autoship_group.py` -> `autoship_queue.py` pipeline instead of the old
single `autoship_discover.py` call.

Plan: plans/autoship-issue-batching.md — Slice 3, Step 3.1.

This is an intentionally intermediate state: Step 3's per-issue loop prose
is not updated in this slice (that's Slice 6's job, later in the same plan)
— it still describes the old `{number, title}` array shape. Step 2's prose
must name that gap explicitly rather than silently imply Step 3 already
consumes the new queue shape.
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


def test_step_2_pipes_group_output_into_queue_script():
    section_text = collapsed(_step_2_section())
    assert grep(r"autoship_group\.py.*\|\s*python3.*autoship_queue\.py", section_text)


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


# --- 7. Step 3 transition gap named explicitly -------------------------------


def test_step_2_names_step_3_transition_gap_for_old_shape():
    section_text = collapsed(_step_2_section())
    assert grep(
        r"Step 3's prose below is still written for the old "
        r"`\{number, title\}` shape",
        section_text,
    )
    assert grep(
        r"has not yet been\s*updated to consume this new queue shape", section_text
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


# --- 11. Fix 4: Step 3 forward-pointer note --------------------------------


def _step_3_section():
    return section(_text(), r"^## Step 3", boundary_pattern=r"^## Step 4")


def test_step_3_opens_with_forward_pointer_to_shape_mismatch():
    section_text = collapsed(_step_3_section())
    assert grep(
        r"this step's prose still assumes the old `\{number, title\}` "
        r"per-issue shape",
        section_text,
    )
    assert grep(r"see Step 2's discovery pipeline", section_text)
    assert grep(
        r"has not yet been updated to consume the `queue` array's "
        r"`batch`/`solo` dispatch units",
        section_text,
    )


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
