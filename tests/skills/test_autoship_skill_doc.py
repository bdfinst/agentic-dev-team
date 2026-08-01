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

from skill_doc_helpers import PLUGIN_ROOT, collapsed, grep, section

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
