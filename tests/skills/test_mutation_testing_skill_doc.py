"""Doc-shape contract for issue #521 additions to the /mutation-testing
skill: honest score, claimed score, timeout warning, NoCoverage-first
triage, mutation-type-aware guidance, and probe-file selection.

Plan: plans/mutation-testing-honest-score-and-triage.md — Slice 1
(SKILL.md) and Slice 2 (csharp-stryker-net.md).

Section guards against the SKILL.md / language-reference prose. The prose
is the deliverable; these guards regress when the contract drifts.

Ported from tests/skills/mutation_testing_skill_doc_tests.bats (issue #674).
"""

from __future__ import annotations

from skill_doc_helpers import (
    PLUGIN_ROOT,
    grep,
    section,
    section_outside_code,
)

MUTATION_TESTING = PLUGIN_ROOT / "skills" / "mutation-testing"
SKILL = MUTATION_TESTING / "SKILL.md"
CSHARP = MUTATION_TESTING / "references" / "languages" / "csharp-stryker-net.md"


def _text() -> str:
    return SKILL.read_text()


def _csharp_text() -> str:
    return CSHARP.read_text()


def _output_format_section() -> str:
    # Ignores ## headings inside fenced code blocks (the ```markdown
    # example contains "## Mutation Testing Results" etc.).
    return section_outside_code(_text(), r"^## Output format")


def _machine_readable_section() -> str:
    return section(
        _text(),
        r"^## Machine-readable output",
        boundary_pattern=r"^## ",
        include_start_line=False,
    )


def _step_4_section() -> str:
    return section(
        _text(), r"^## Step 4", boundary_pattern=r"^## ", include_start_line=False
    )


# --- Slice 1 · AC-1: honest score above claimed score in Output format -------


def test_skill_output_format_shows_honest_score_line():
    assert "Honest score" in _output_format_section()


def test_skill_output_format_shows_claimed_score_line():
    assert "Claimed score" in _output_format_section()


def test_skill_honest_score_line_appears_above_claimed_score_line_in_output_format():
    lines = _output_format_section().splitlines()
    honest_idx = next((i for i, ln in enumerate(lines) if "Honest score" in ln), None)
    claimed_idx = next((i for i, ln in enumerate(lines) if "Claimed score" in ln), None)
    assert honest_idx is not None
    assert claimed_idx is not None
    assert honest_idx < claimed_idx


# --- Slice 1 · AC-2: schema example carries the five new fields --------------


def test_skill_machine_readable_output_schema_names_honest_score():
    assert '"honest_score"' in _machine_readable_section()


def test_skill_machine_readable_output_schema_names_claimed_score():
    assert '"claimed_score"' in _machine_readable_section()


def test_skill_machine_readable_output_schema_names_timeout_pct():
    assert '"timeout_pct"' in _machine_readable_section()


def test_skill_machine_readable_output_schema_names_no_coverage():
    assert '"no_coverage"' in _machine_readable_section()


def test_skill_machine_readable_output_schema_names_timeout_warning():
    assert '"timeout_warning"' in _machine_readable_section()


# --- Slice 1 · AC-3: formulas documented next to the schema ------------------


def test_skill_schema_section_shows_the_honest_score_formula():
    assert grep(
        r"honest_score[[:space:]]*=[[:space:]]*Killed[[:space:]]*/[[:space:]]*"
        r"\(Killed[[:space:]]*\+[[:space:]]*Survived[[:space:]]*\+[[:space:]]*NoCoverage\)",
        _machine_readable_section(),
    )


def test_skill_schema_section_shows_the_claimed_score_formula():
    assert grep(
        r"claimed_score[[:space:]]*=[[:space:]]*\(Killed[[:space:]]*\+[[:space:]]*Timeout\)"
        r"[[:space:]]*/[[:space:]]*\(Killed[[:space:]]*\+[[:space:]]*Survived[[:space:]]*\+"
        r"[[:space:]]*Timeout[[:space:]]*\+[[:space:]]*NoCoverage\)",
        _machine_readable_section(),
    )


# --- Slice 1 · AC-4: schema_version stays at 1 -------------------------------


def test_skill_schema_version_stays_at_1_no_bump_to_2_anywhere():
    assert not grep(r'"schema_version"[[:space:]]*:[[:space:]]*2', _text())


# --- Slice 1 · AC-5: timeout warning defined and remediation named ----------


def test_skill_schema_section_names_the_timeout_warning_threshold_0_05_5_pct():
    assert grep(
        r"timeout_pct[[:space:]]*>[[:space:]]*0\.05", _machine_readable_section()
    )


def test_skill_timeout_warning_names_additional_timeout_as_the_fix():
    assert "additional-timeout" in _text()


# --- Slice 1 · AC-6: emitting-adapters list ---------------------------------
#
# These tests must guard the AC-6 "Emitting adapters" paragraph, NOT the
# pre-existing native-report cross-link that happens to also name the
# adapters. Scope each check to a window that starts at the "Emitting
# adapters" heading in the Machine-readable output section.


def test_skill_emitting_adapters_paragraph_exists_in_the_schema_section():
    assert grep(r"[Ee]mitting adapters", _machine_readable_section())


def _emitting_adapters_window() -> str:
    s = _machine_readable_section()
    idx = None
    for pat in ("Emitting adapters", "emitting adapters"):
        found = s.find(pat)
        if found != -1:
            idx = found
            break
    assert idx is not None
    return s[idx:]


def test_skill_emitting_adapters_paragraph_names_stryker_net_as_an_emitter():
    assert "Stryker.NET" in _emitting_adapters_window()


def test_skill_emitting_adapters_paragraph_names_pitest_as_an_emitter():
    assert "pitest" in _emitting_adapters_window()


def test_skill_emitting_adapters_paragraph_names_mutmut_as_an_emitter():
    assert "mutmut" in _emitting_adapters_window()


def test_skill_emitting_adapters_paragraph_notes_go_mutesting_omits_the_new_fields_advisory_only():
    w = _emitting_adapters_window()
    assert "go-mutesting" in w
    assert "omit" in w


# --- Slice 1 · AC-7: NoCoverage is a first-class triage category ------------


def test_skill_step_4_triage_table_has_a_nocoverage_row():
    assert r"| **NoCoverage** |" in _step_4_section()


def test_skill_nocoverage_rows_action_tells_operator_to_add_a_test_that_reaches_the_path():
    s = _step_4_section()
    assert "NoCoverage" in s
    assert "reaches" in s
    assert "path" in s


def test_skill_step_4_recommended_work_order_lists_nocoverage_before_survived():
    # Find the "Recommended work order" prose in Step 4 and check ordering
    # by line number.
    lines = _step_4_section().splitlines()
    order_start = next(
        (i for i, ln in enumerate(lines) if "Recommended work order" in ln), None
    )
    assert order_start is not None
    nocov_idx = next(
        (i for i in range(order_start, len(lines)) if "NoCoverage" in lines[i]), None
    )
    surv_idx = next(
        (i for i in range(order_start, len(lines)) if "Survived" in lines[i]), None
    )
    assert nocov_idx is not None
    assert surv_idx is not None
    assert nocov_idx < surv_idx


# --- Slice 1 · AC-8: mutation-type-aware sub-section ------------------------


def test_skill_step_4_has_a_mutation_type_aware_sub_section():
    assert grep(r"^### .*[Mm]utation-type-aware", _step_4_section())


def _mutation_type_aware_section() -> str:
    return section(
        _text(),
        r"^### .*[Mm]utation-type-aware",
        boundary_pattern=r"^### ",
        include_start_line=False,
    )


def test_type_aware_guidance_covers_string_objectinitializer_equality_specific_assertion():
    s = _mutation_type_aware_section()
    assert "String" in s
    assert "ObjectInitializer" in s
    assert "Equality" in s


def test_type_aware_guidance_names_statement_block_and_states_a_stronger_assertion_cannot_kill_them():
    s = _mutation_type_aware_section()
    assert "Statement" in s
    assert "Block" in s
    assert "cannot kill" in s


def test_type_aware_guidance_names_guard_and_directs_to_unit_test_invoking_the_guarded_method_directly():
    s = _mutation_type_aware_section()
    assert "Guard" in s
    assert "directly" in s


# --- Slice 1 · AC-9: language-agnostic probe file selection in Step 2 -------


def _step_2_section() -> str:
    return section(
        _text(), r"^## Step 2", boundary_pattern=r"^## ", include_start_line=False
    )


def test_skill_step_2_has_a_probe_file_selection_sub_section():
    assert grep(r"^### .*[Pp]robe file selection", _step_2_section())


def _probe_file_selection_section() -> str:
    return section(
        _text(),
        r"^### .*[Pp]robe file selection",
        boundary_pattern=r"^#{2,3} ",
        include_start_line=False,
    )


def test_skill_probe_selection_names_the_50_mutants_rule():
    s = _probe_file_selection_section()
    assert "50" in s
    assert "mutants" in s


def test_skill_probe_selection_names_the_highest_existing_score_rule():
    s = _probe_file_selection_section()
    assert grep(r"[Hh]ighest", s)
    assert "score" in s


def test_skill_probe_selection_lists_generated_code_dtos_and_near_zero_coverage_as_anti_patterns():
    s = _probe_file_selection_section()
    assert grep(r"[Gg]enerated", s)
    assert "DTO" in s
    assert grep(r"[Cc]overage", s)


# --- Slice 2 · AC-10: C#-specific probe avoidance in the language reference -


def test_csharp_reference_has_a_probe_file_selection_sub_section():
    assert grep(r"^### .*[Pp]robe file selection", _csharp_text())


def _csharp_probe_file_selection_section() -> str:
    return section_outside_code(
        _csharp_text(),
        r"^### .*[Pp]robe file selection",
        boundary_pattern=r"^#{2,3} ",
    )


def test_csharp_probe_avoidance_names_grpc_protobuf_objectinitializer_compileerror_failure_mode():
    s = _csharp_probe_file_selection_section()
    assert grep(r"(gRPC|Protobuf)", s)
    assert "ObjectInitializer" in s
    assert "CompileError" in s


def test_csharp_probe_avoidance_names_caching_standard_mutation_level_failure_mode():
    s = _csharp_probe_file_selection_section()
    assert grep(r"[Cc]aching", s)
    assert "Standard" in s


def test_csharp_probe_avoidance_names_the_specific_non_existent_methods_stringbuilder_prepend_idictionary_sum():
    s = _csharp_probe_file_selection_section()
    assert "StringBuilder.Prepend" in s
    assert "IDictionary.Sum" in s


def test_csharp_probe_file_section_cross_links_back_to_skill_md_step_2_for_the_language_agnostic_rule():
    s = _csharp_probe_file_selection_section()
    assert "SKILL.md" in s
    assert "Step 2" in s


# --- Issue #1369: "accepted" survivor status + reason + dual raw/adjusted
# score ------------------------------------------------------------------


def test_skill_schema_documents_status_accepted_on_survivor_entries():
    assert '"accepted"' in _machine_readable_section()


def test_skill_schema_requires_a_reason_string_on_accepted_and_equivalent_entries():
    s = _machine_readable_section()
    assert grep(r"reason", s, ignore_case=True)
    assert grep(r"equivalent.{0,80}reason|reason.{0,80}equivalent", s, ignore_case=True)
    assert grep(r"accepted.{0,80}reason|reason.{0,80}accepted", s, ignore_case=True)


def test_skill_callers_must_filter_accepted_alongside_equivalent():
    s = _machine_readable_section()
    assert grep(r"filter.+equivalent.+accepted|equivalent.+accepted.+filter", s, ignore_case=True)


def test_skill_schema_section_shows_the_raw_score_and_adjusted_score_formulas():
    s = _machine_readable_section()
    assert grep(
        r"raw_score[[:space:]]*=[[:space:]]*Killed[[:space:]]*/[[:space:]]*"
        r"\(Killed[[:space:]]*\+[[:space:]]*Survived[[:space:]]*\+[[:space:]]*NoCoverage\)",
        s,
    )
    assert grep(
        r"adjusted_score[[:space:]]*=[[:space:]]*Killed[[:space:]]*/[[:space:]]*"
        r"\(Killed[[:space:]]*\+[[:space:]]*\(Survived[[:space:]]*-[[:space:]]*Accepted\)"
        r"[[:space:]]*\+[[:space:]]*NoCoverage\)",
        s,
    )


def test_skill_step_4_table_has_an_equivalent_row_and_an_accepted_this_pass_row():
    s = _step_4_section()
    assert r"| **Equivalent** |" in s
    assert r"| **Accepted this pass** |" in s


def test_skill_step_4_accepted_row_requires_per_mutant_reason_not_file_level_wave_off():
    s = _step_4_section()
    idx = s.find("**Accepted this pass**")
    assert idx != -1
    window = s[idx : idx + 400]
    assert "reason" in window
    assert "file-level" in window


def test_skill_output_format_shows_raw_and_adjusted_score_line():
    s = _output_format_section()
    assert "Raw:" in s
    assert "Adjusted" in s


def test_skill_output_format_has_an_accepted_survivors_deferred_table():
    assert "Accepted Survivors (deferred)" in _output_format_section()


# --- Issue #1906/#1912 Slice 1 Step 1.2: mirror mutation-kill.md's
# line-clustering instruction in the Step 4 triage guidance -----------------
#
# These tests must guard the "Cluster survivors by source line" paragraph
# specifically, NOT anywhere else in the whole (~87-line) Step 4 section —
# a future edit could add an unrelated `mutation-kill.md` mention elsewhere
# in Step 4 and still leave this guard green even if the clustering
# paragraph's own cross-link were deleted. Same hazard, same fix, as the
# "Emitting adapters" window above.


def _line_clustering_window() -> str:
    s = _step_4_section()
    idx = s.find("Cluster survivors by source line")
    assert idx != -1
    # Bound by the paragraph itself (next blank line), not a fixed char
    # count — a fixed count has near-zero slack against future trims of
    # this paragraph and risks silently re-widening into the next section.
    return s[idx:].split("\n\n", 1)[0]


def test_skill_step_4_references_line_clustering_approach():
    w = _line_clustering_window()
    assert grep(r"[Cc]luster", w)
    assert "survivors-per-line descending" in w
    assert "not total mutants-per-line" in w


def test_skill_step_4_line_clustering_covers_same_or_adjacent_line():
    assert grep(r"same or adjacent source line", _line_clustering_window())


def test_skill_step_4_line_clustering_prefers_one_test_per_cluster():
    w = _line_clustering_window()
    assert "one test per cluster where feasible" in w
    assert "rather than one per mutant" in w


def test_skill_step_4_line_clustering_cross_references_mutation_kill_md():
    assert "mutation-kill.md" in _line_clustering_window()
