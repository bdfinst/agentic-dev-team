"""#811 — /build's inline review checkpoints run a shared static-analysis
self-heal pass before the semantic review sequence, and the mechanism
(scoping, lanes, shared fix loop, 2-attempt cap, detection ladder,
granularity, ordering, metrics fold, opt-out) is specified in exactly one
place: the build skill's static-self-heal reference. Documentation gates
over the skill prose — the language issues (#807–#810) contribute tools,
never mechanism.
"""

from __future__ import annotations

import re

from skill_doc_helpers import PLUGIN_ROOT, grep, section

BUILD = PLUGIN_ROOT / "skills" / "build" / "SKILL.md"
MECHANISM = PLUGIN_ROOT / "skills" / "build" / "references" / "static-self-heal.md"


def _build_text() -> str:
    return BUILD.read_text()


def _mechanism_text() -> str:
    return MECHANISM.read_text()


def _mechanism_flat() -> str:
    """Whitespace-normalized mechanism text — phrase assertions must not
    depend on where prose happens to line-wrap."""
    return re.sub(r"\s+", " ", _mechanism_text())


def _complex_bullet() -> str:
    """The `complex` granularity bullet of sub-step 4 (per-step checkpoint)."""
    lines = _build_text().splitlines()
    start = next(
        i for i, ln in enumerate(lines) if re.search(r"^\s*-\s+\*\*complex\*\*:", ln)
    )
    out = [lines[start]]
    for ln in lines[start + 1 :]:
        if re.match(r"^\s*-\s+", ln) or re.match(r"^\s*\d+\.\s+", ln):
            break
        out.append(ln)
    return "\n".join(out)


def _slice_checkpoint_item() -> str:
    """Sub-step 6 (batched slice review checkpoint) of step 4's list."""
    return section(
        _build_text(),
        r"^6\.\s+\*\*Slice review checkpoint",
        boundary_pattern=r"^7\.\s+",
    )


# --- checkpoint wiring: exactly the two existing sites, static before semantic


def test_mechanism_reference_file_exists():
    assert MECHANISM.is_file()


def test_per_step_complex_checkpoint_runs_static_pass_before_spec_compliance():
    bullet = _complex_bullet()
    assert "static self-heal" in bullet
    assert "spec-compliance-review" in bullet
    assert bullet.index("static self-heal") < bullet.index("spec-compliance-review")


def test_slice_boundary_checkpoint_runs_static_pass_before_spec_compliance():
    item = _slice_checkpoint_item()
    assert "static self-heal" in item
    assert "spec-compliance-review" in item
    assert item.index("static self-heal") < item.index("spec-compliance-review")


def test_both_checkpoint_sites_point_to_the_mechanism_reference():
    for text in (_complex_bullet(), _slice_checkpoint_item()):
        assert "references/static-self-heal.md" in text


def test_no_build_step_other_than_the_two_checkpoints_references_the_pass():
    """AC: exactly the two existing checkpoint sites — within `## Steps`,
    every self-heal mention sits inside the complex bullet or the slice
    checkpoint item, nowhere else. (Orchestrator constraint 5's one-line
    checkpoint summary sits outside the steps and is not a third site.)"""
    steps_text = section(
        _build_text(), r"^## Steps", boundary_pattern=r"^## Escalation"
    )
    inside = _complex_bullet() + "\n" + _slice_checkpoint_item()
    inside_count = inside.count("self-heal")
    steps_count = steps_text.count("self-heal")
    assert steps_count > 0
    assert steps_count == inside_count


# --- scoping: the two-case rule, re-resolution, partitioning


def test_per_step_scope_is_working_tree_vs_head_plus_untracked():
    text = _mechanism_text()
    assert "git diff --name-only --diff-filter=ACM HEAD" in text
    assert "git ls-files --others --exclude-standard" in text


def test_slice_scope_is_anchored_at_slice_start_sha():
    text = _mechanism_text()
    assert "slice_start_sha" in text
    assert "git rev-parse HEAD" in text


def test_deletions_are_excluded_from_scope_deliberately():
    text = _mechanism_text()
    assert "--diff-filter=ACM" in text
    assert grep(r"delet", text, ignore_case=True)


def test_scope_is_re_resolved_at_the_start_of_each_retry_attempt():
    assert grep(r"re-resolve", _mechanism_text(), ignore_case=True)


def test_files_partition_by_registered_lane_extensions_never_a_hard_coded_list():
    text = _mechanism_text()
    assert grep(r"partition", text, ignore_case=True)
    assert grep(r"hard-cod", text, ignore_case=True)


def test_empty_lane_partition_is_never_dispatched():
    assert "no lane tool is ever invoked with an empty file list" in _mechanism_flat()


# --- the shared fix loop and its cap


def test_shared_loop_orders_prefix_then_verify_then_agent_handoff():
    text = _mechanism_text()
    for phrase in ("autofix", "verify", "coding agent"):
        assert phrase in text, f"missing loop element: {phrase}"


def test_loop_escalates_after_exactly_two_agent_fix_attempts():
    text = _mechanism_text()
    assert grep(r"attempt > 2", text) or grep(r"2 agent-fix attempts", text)


def test_attempt_counters_are_per_lane_per_checkpoint_and_independent():
    text = _mechanism_text()
    assert grep(r"per lane, per checkpoint", text, ignore_case=True)
    assert grep(r"independent", text, ignore_case=True)


def test_passed_lane_stays_passed_no_cross_lane_re_verify():
    assert "stays passed" in _mechanism_flat()


def test_tests_re_run_after_agent_fix_edits_before_next_verify():
    text = _mechanism_text()
    assert grep(r"re-run the tests", text, ignore_case=True)


def test_escalation_carries_a_root_cause_diagnosis_not_an_attempt_count():
    text = _mechanism_text()
    assert grep(r"Systematic Debugging", text)
    assert grep(r"diagnos", text, ignore_case=True)


# --- opt-out toggle


def test_opt_out_toggle_short_circuits_before_any_probe_with_one_info_line():
    text = _mechanism_text()
    assert "DEV_TEAM_STATIC_SELF_HEAL=off" in text
    assert grep(r"before any probe", text, ignore_case=True)
    assert grep(r"info line", text, ignore_case=True)


def test_any_other_toggle_value_or_unset_leaves_the_pass_enabled():
    assert grep(r"any other value \(or unset\)", _mechanism_text(), ignore_case=True)


# --- detection, binding, and degradation


def test_slots_are_probed_once_per_build_run_and_cached():
    text = _mechanism_text()
    assert grep(r"once per `/build` run", text) or grep(r"once per /build run", text)
    assert grep(r"cache", text, ignore_case=True)


def test_detection_walks_the_ordered_provider_list_and_binds_the_first_match():
    text = _mechanism_text()
    assert grep(r"ordered provider list", text, ignore_case=True)
    assert grep(r"bind", text, ignore_case=True)


def test_binding_never_displaces_an_existing_configured_tool():
    assert grep(r"bind, don't replace", _mechanism_text(), ignore_case=True)


def test_probes_check_repo_local_locations_before_path():
    text = _mechanism_text()
    assert grep(r"repo-local", text, ignore_case=True)
    assert "PATH" in text


def test_qualification_contract_lists_all_four_items():
    text = _mechanism_text()
    assert grep(r"scoped file list", text, ignore_case=True)
    assert grep(r"machine-readable", text, ignore_case=True)
    assert grep(r"40 LOC", text)
    assert grep(r"latency", text, ignore_case=True)
    assert grep(r"deterministic exit codes", text, ignore_case=True)


def test_qualifying_but_slow_provider_is_demoted_to_slice_boundary_granularity():
    text = _mechanism_text()
    assert grep(r"demot", text, ignore_case=True)
    assert grep(r"slice-boundary", text, ignore_case=True)
    assert grep(r"fast default", text, ignore_case=True)


def test_a_present_tool_failing_the_contract_binds_nothing():
    assert grep(r"binds nothing", _mechanism_text(), ignore_case=True)


def test_all_four_degradation_rungs_are_documented_and_none_fails_the_checkpoint():
    text = _mechanism_text()
    assert grep(r"diagnose-only", text, ignore_case=True)  # rung 1
    assert grep(r"check mode", text, ignore_case=True)  # rung 2
    assert grep(r"install.hint", text, ignore_case=True)  # rung 3
    assert grep(r"treat as missing", text, ignore_case=True)  # rung 4
    assert grep(r"[Nn]ever a failure", text)


def test_rung_three_hints_are_repo_level_installs_with_a_project_init_pointer():
    text = _mechanism_text()
    assert grep(r"repo-level", text, ignore_case=True)
    assert "/project-init" in text


# --- C# accommodation


def test_csharp_sarif_is_filtered_post_hoc_to_the_changed_file_set():
    text = _mechanism_text()
    assert "ErrorLog" in text
    assert grep(r"post-hoc", text, ignore_case=True)


def test_csharp_stale_sarif_triggers_a_rebuild_before_filtering():
    text = _mechanism_text()
    assert grep(r"re-run `dotnet build`", text) or grep(r"regenerate", text, ignore_case=True)


# --- ordering and context injection


def test_static_outcome_is_injected_with_the_do_not_re_report_framing():
    assert "Do not re-report these issues" in _mechanism_text()


# --- metrics fold


def test_metrics_fold_into_the_existing_review_value_sensor():
    text = _mechanism_text()
    assert "metrics/review-value.jsonl" in text
    assert "agents_run" in text
    assert "fix_iterations" in text
    assert '"escalated"' in text
    assert "DEV_TEAM_REVIEW_VALUE=off" in text


# --- placement and the zero-lane no-op


def test_pass_binds_to_existing_checkpoints_only_trivial_slices_get_none():
    text = _mechanism_text()
    assert grep(r"trivial", text, ignore_case=True)
    assert grep(r"backstop", text, ignore_case=True)


def test_zero_registered_lanes_is_a_structural_no_op():
    text = _mechanism_text()
    assert grep(r"zero", text, ignore_case=True)
    assert grep(r"no-op", text, ignore_case=True)


def test_mechanism_points_at_the_build_time_lanes_registry():
    assert grep(r"Build-time lanes", _mechanism_text())
