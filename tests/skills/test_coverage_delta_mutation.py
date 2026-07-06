"""Doc-shape contract for /coverage-delta's scoped mutation step (Slice 2 of
plans/mutation-testing-every-phase.md, issue #285).

The worker measures and reports; it never halts on net-new survivors.
These tests guard the doc-only invariants: the gating flags, the four
status values, the policy-free assertion, and atomic-write semantics for
mutation-history.json.

Note on the concurrent-write Gherkin scenario: it is asserted at the
documentation level only (SKILL.md prescribes temp-file-then-rename and
forbids direct overwrite). Behavioral atomicity is verified by code
review, not by this RED gate. See Slice 2 RED notes in the plan.

Ported from tests/skills/coverage_delta_mutation_tests.bats (issue #674).
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, grep, section

SKILL = PLUGIN_ROOT / "skills" / "coverage-delta" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text()


def _step_2b() -> str:
    # Extract the Step 2b body — from the `### 2b.` heading up to the next
    # `### N.` step heading or the next `##` section. Mirrors the step2()
    # helper pattern in test_quality_targets_converge_mutation_reuse.py.
    return section(
        _text(),
        r"^### 2b\.",
        boundary_pattern=r"^### \d+\b|^## ",
        include_start_line=False,
    )


def _parse_arguments_section() -> str:
    return section(
        _text(),
        r"^## Parse Arguments",
        boundary_pattern=r"^## ",
        include_start_line=False,
    )


# --- Flag surface -----------------------------------------------------------


def test_skill_parse_arguments_names_story_files():
    assert "--story-files" in _parse_arguments_section()


def test_skill_parse_arguments_names_story_pre_existing():
    assert grep(r"--story", _parse_arguments_section())


# --- Step 2b gating: both --story AND --story-files must be present --------


def test_skill_has_a_step_2b_measure_scoped_mutation_heading():
    # The literal "Step 2b" appears in body prose as well; tighten to the
    # actual heading line so we regress when someone removes the section
    # but leaves a dangling reference.
    assert grep(r"^### 2b\.", _text())


def test_skill_step_2b_body_names_both_story_and_story_files_as_gating_conditions():
    body = _step_2b()
    assert "--story-files" in body
    assert grep(r"--story\b", body)


def test_skill_step_2b_invokes_mutation_testing_with_workflow_managed_approval():
    assert "--workflow-managed-approval" in _step_2b()


# --- Worker policy: measurement only, never halts ---------------------------


def test_skill_explicit_statement_worker_measures_does_not_halt_on_net_new_survivors():
    # The plan pins this literal sentence (or substring-equivalent) as the
    # worker/policy boundary. Drift here means a reviewer can't tell
    # whether the worker or orchestrator owns the gate.
    assert grep(r"measures.+reports.+(NOT|does not).+halt", _text())


def test_skill_documents_exit_code_0_on_net_new_survivors_non_zero_only_on_tool_failure():
    assert grep(
        r"exit (code )?0.*net.new|net.new.*exit (code )?0|non-zero.*tool (execution )?failure",
        _text(),
        ignore_case=True,
    )


# --- Status enum -----------------------------------------------------------


def test_skill_documents_status_enum_ok_net_new_survivors_first_measurement_tool_unavailable():
    text = _text()
    for val in ("ok", "net_new_survivors", "first_measurement", "tool_unavailable"):
        assert grep(rf'"?{val}"?', text), f"missing status value: {val}"


def test_skill_documents_skipped_empty_scope_as_an_additional_worker_only_state():
    assert "skipped_empty_scope" in _text()


# --- Baseline-of-record rule -----------------------------------------------


def test_skill_documents_most_recent_mutation_history_entry_per_file_is_the_baseline_of_record():
    assert grep(
        r"most recent.+(history|entry).+(file|baseline)|baseline.of.record",
        _text(),
        ignore_case=True,
    )


def test_skill_documents_first_measurement_survivors_before_null_delta_null():
    assert grep(
        r"first.measurement|survivors_before.+null|first measurement",
        _text(),
        ignore_case=True,
    )


# --- Equivalent-mutant filter ----------------------------------------------


def test_skill_documents_filtering_status_equivalent_before_computing_delta():
    assert grep(
        r"filter.+equivalent|equivalent.+(filter|exclude)|exclude.+equivalent",
        _text(),
        ignore_case=True,
    )


# --- Atomic-write semantics for mutation-history.json ----------------------


def test_skill_documents_mutation_history_json_as_the_per_file_history_file():
    assert "mutation-history.json" in _text()


def test_skill_documents_temp_file_then_rename_idiom_for_mutation_history_json():
    # Concurrent-write Gherkin scenario asserted at doc level only.
    assert grep(
        r"temp(-| )file.+rename|rename.+temp(-| )file|atomic.+(write|rename)",
        _text(),
        ignore_case=True,
    )


# --- Tool-unavailable degradation surfaces /setup --------------------------


def test_skill_tool_unavailable_result_block_names_setup_as_install_path():
    assert "/setup" in _text()


def test_skill_documents_tool_disappears_mid_run_scenario_records_prior_tool():
    assert "prior_tool" in _text()


# --- Result block schema on stdout -----------------------------------------


def test_skill_documents_json_result_block_with_status_mutation_story_story_files():
    text = _text()
    for key in ("status", "mutation", "story", "story_files"):
        assert grep(rf'"?{key}"?', text), f"missing result-block key: {key}"


# --- Convergence-loop reuse: --story alone (no --story-files) is a no-op ---


def test_skill_story_without_story_files_triggers_no_mutation_run_convergence_loop_callable():
    # The Slice 2 contract: without --story-files, no scoped mutation, no
    # mutation-history.json write. This preserves the existing
    # /quality-targets-converge call path.
    assert grep(
        r"(without|no).+--story-files.+(no|skip).+(mutation|history)|--story alone",
        _text(),
        ignore_case=True,
    )


# --- --story-files glob matches zero files ----------------------------------


def test_skill_documents_skipped_empty_scope_for_empty_story_files_glob():
    assert grep(
        r"empty.+(--story-files|scope)|skipped_empty_scope", _text(), ignore_case=True
    )


def test_skill_documents_history_entry_write_on_empty_story_files_scope():
    # Gherkin 'Then' for the empty-scope scenario: mutation-history GETS an
    # entry with status:'skipped_empty_scope'. The doc must say so or
    # operators can't tell whether the worker silently dropped the Story.
    assert grep(r"one history entry|history entry recorded", _text(), ignore_case=True)


# --- Markdown row template gains a Mutants column --------------------------


def test_skill_parent_issue_markdown_row_template_includes_a_mutants_column():
    assert grep(r"[Mm]utants.*Δ|Δ.*[Mm]utants|Mutants <count>", _text())
