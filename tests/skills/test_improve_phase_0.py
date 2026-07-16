"""Contract for the /test-improve skill Phase 0 (approach contract).

Issue #536 — consolidation of /test-modernize + /test-upgrade. Slice 1 of
the orchestrator plan: skeleton + Phase 0 only. Subsequent phases (1..7)
are added in later slices.

Ported from tests/skills/test_improve_phase_0_tests.bats (issue #674).
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, frontmatter, grep

SKILL = PLUGIN_ROOT / "skills" / "test-improve" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text()


def test_test_improve_skill_md_exists():
    assert SKILL.is_file()


def test_frontmatter_declares_name_test_improve():
    fm = frontmatter(_text())
    assert grep(r"^name: *test-improve", fm)


def test_frontmatter_declares_role_orchestrator():
    fm = frontmatter(_text())
    assert grep(r"^role: *orchestrator", fm)


def test_frontmatter_declares_user_invocable_true():
    fm = frontmatter(_text())
    assert grep(r"^user-invocable: *true", fm)


def test_argument_hint_documents_all_five_flags_in_the_expected_shape():
    fm = frontmatter(_text())
    hint_lines = [line for line in fm.splitlines() if grep(r"^argument-hint:", line)]
    assert hint_lines
    hint = hint_lines[0]
    assert grep(r"<repo-path>", hint)
    assert grep(r"--parent", hint)
    assert grep(r"--analyze-only", hint)
    assert grep(r"--from-phase", hint)
    assert grep(r"--stack", hint)


def test_frontmatter_declares_allowed_tools():
    fm = frontmatter(_text())
    assert grep(r"^allowed-tools:", fm)


def test_body_contains_a_phase_0_section_header():
    assert grep(r"^### Phase 0", _text())


def test_phase_0_prompt_battery_names_mutation_on_off_knob_default_off():
    text = _text()
    assert grep(r"mutation", text, ignore_case=True)
    assert grep(
        r"mutation.*(default[^.]*off|off.*default)|default[^.]*off.*mutation",
        text,
        ignore_case=True,
    )


def test_phase_0_prompt_battery_names_bdd_rubric_default_none():
    text = _text()
    assert grep(r"BDD.*rubric|rubric", text, ignore_case=True)
    assert grep(r"default.*none|none.*default", text, ignore_case=True)


def test_phase_0_prompt_battery_names_refactor_mode_default_no_refactor():
    text = _text()
    assert grep(r"no-refactor", text)
    assert grep(r"refactor-allowed", text)
    assert grep(
        r"refactor.*(default[^.]*no-refactor|no-refactor.*default)",
        text,
        ignore_case=True,
    )


def test_phase_0_prompt_battery_names_quality_targets_knob():
    assert grep(r"quality target", _text(), ignore_case=True)


def test_phase_0_prompt_battery_names_sink_parent_vs_local():
    text = _text()
    assert grep(r"--parent", text)
    assert grep(r"local.files|local-files|local files", text, ignore_case=True)


# --- #1108: knob 6, the all-or-none code-lookup install ----------------------


def test_phase_0_has_code_lookup_install_knob_all_or_none():
    text = _text()
    assert grep(r"all-or-none", text)
    assert grep(r"CodeGraph", text) and grep(r"Repowise", text) and grep(r"Graphify", text)


def test_knob_6_recommends_yes_when_missing():
    assert grep(r"[Rr]ecommended.*yes|yes.*when any of the three is\s+missing", _text())


def test_knob_6_is_explicit_choice_opting_out_of_enter_all():
    text = _text()
    # Explicit y/n, and a blank answer re-prompts rather than defaulting.
    assert grep(r"explicit `?y`?/`?n`?", text, ignore_case=True)
    assert grep(r"blank.*re-?prompt", text, ignore_case=True)
    assert grep(r"exception", text, ignore_case=True)  # the Enter-accepts-all carve-out


def test_knob_6_discloses_graphify_repo_write():
    text = _text()
    assert grep(r"CLAUDE\.md", text) and grep(r"git hooks", text)


def test_knob_6_delegates_install_to_project_init():
    assert grep(r"/project-init", _text())


def test_knob_6_decline_is_visibly_confirmed():
    assert grep(r"fall back to Read/Grep/Glob", _text())


def test_knob_6_is_idempotent_and_records_partial_failure():
    text = _text()
    assert grep(r"already present", text)
    assert grep(r"missing", text, ignore_case=True)
    assert grep(r"partial", text, ignore_case=True)
    assert grep(r"per-tool", text, ignore_case=True)


def test_enter_accepts_every_default_in_one_keystroke():
    assert grep(
        r"Enter[^.]*accept.*default|accept.*default.*Enter|one keystroke",
        _text(),
        ignore_case=True,
    )


def test_go_advisory_is_present_go_mutesting_alpha_survivor_count_not_a_gate_go_test_fuzz():
    text = _text()
    assert grep(r"go-mutesting", text, ignore_case=True)
    assert grep(r"alpha", text, ignore_case=True)
    assert grep(r"survivor count.*not.*gate|not a gate", text, ignore_case=True)
    assert grep(r"go test -fuzz|-fuzz", text, ignore_case=True)


def test_phase_0_persistence_target_is_memory_test_improve_slug_phase_0_md():
    assert grep(r"memory/test-improve/<slug>/phase-0\.md", _text())


def test_phase_0_md_must_exist_before_phase_1_runs():
    assert grep(
        r"phase-0\.md.*(before|prior to).*(phase 1|Phase 1)|"
        r"(before|prior to).*Phase 1.*phase-0\.md",
        _text(),
        ignore_case=True,
    )


def test_from_phase_semantics_documented_skips_completed_phases():
    text = _text()
    assert grep(r"--from-phase", text)
    assert grep(r"from-phase.*(skip|resume)", text, ignore_case=True)


def test_analyze_only_semantics_documented_exits_after_phase_1():
    text = _text()
    assert grep(r"--analyze-only", text)
    assert grep(r"analyze-only.*(exit|after Phase 1)", text, ignore_case=True)


def test_phase_start_banner_requirement_documented_phase_n_7_with_settings_recap():
    text = _text()
    assert grep(r"Phase N/7", text)
    assert grep(r"mutation:.*binding:.*refactor:.*sink:", text, ignore_case=True)


def test_phase_0_answer_immutability_documented():
    text = _text()
    assert grep(r"immutable", text, ignore_case=True)
    assert grep(
        r"from-phase.*not.*re-prompt|not.*re-prompt.*from-phase|"
        r"delete.*phase-0\.md.*re-run",
        text,
        ignore_case=True,
    )


def test_phase_4b_prompt_letter_is_y_b_q_not_r():
    assert grep(r"\[y\].*\[b\].*\[q\]|\[y/b/q\]", _text())
