"""Contract for the /test-improve skill Phase 0 (approach contract).

Issue #536 — consolidation of /test-modernize + /test-upgrade. Slice 1 of
the orchestrator plan: skeleton + Phase 0 only. Subsequent phases (1..7)
are added in later slices.

Ported from tests/skills/test_improve_phase_0_tests.bats (issue #674).
"""

from __future__ import annotations

import re

from skill_doc_helpers import frontmatter, grep, grep_multiline, section
from skill_include_resolver import SKILL
from skill_include_resolver import resolve_test_improve_text as _text


def _phase_start_banner_fence() -> str:
    """The fenced two-line banner literal under '## Phase-start banner' —
    isolated so a regression guard can check the fence's own content instead
    of a substring anywhere in the file (which a mid-sentence backticked
    mention, e.g. explaining what the *old* format looked like, would also
    satisfy)."""
    banner_section = section(_text(), r"^## Phase-start banner", boundary_pattern=r"^## ")
    assert banner_section, "Phase-start banner section not found in test-improve/SKILL.md"
    fence_match = re.search(r"```\n(.*?)\n```", banner_section, re.DOTALL)
    assert fence_match, "no fenced code block found under '## Phase-start banner'"
    return fence_match.group(1)


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


def test_phase_0_mutation_knob_is_three_way_with_kill_loop_default():
    """#1126: the binary mutation on/off knob becomes a three-way mode —
    off / kill-loop (default) / baseline+kill-loop — using one canonical
    token per mode in the prompt, banner, and phase-0.md persistence."""
    text = _text()
    # All three canonical tokens are present.
    assert grep(r"`off`", text)
    assert grep(r"`kill-loop`", text)
    assert grep(r"`baseline\+kill-loop`", text)
    # kill-loop is the default (bracketed default and/or marked default).
    assert grep(r"\[kill-loop\]", text)
    assert grep(r"kill-loop.*default|default.*kill-loop", text, ignore_case=True)


def test_phase_0_mutation_default_change_is_called_out():
    """The Enter-through default changes from no-mutation to the kill loop;
    the prompt must surface this so it is never a silent surprise."""
    text = _text()
    assert grep(r"default change|now performs the mutant-kill loop|mutation now runs by default",
                text, ignore_case=True)


def test_phase_0_banner_uses_the_tristate_mutation_token():
    """The banner recap names the tri-state mutation mode, not on|off."""
    text = _text()
    assert grep(r"mutation:\s*<off\|kill-loop\|baseline\+kill-loop>", text)
    # The old binary banner token must be gone (report: <on|off> is a
    # legitimate separate field, so anchor on the `mutation:` prefix).
    assert not grep(r"mutation:\s*<on\|off>", text)


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


# --- #1412: knob-7 (opt-in baseline-metrics report) is removed --------------


def test_phase_0_prompt_battery_is_six_knobs():
    """#1412: knob-7 (the baseline-metrics-report opt-in) is removed
    entirely, not repurposed — the battery is six knobs, not seven."""
    text = _text()
    assert grep(r"six knobs", text)
    assert not grep(r"seven knobs", text)


def test_phase_0_has_no_baseline_metrics_report_knob():
    """#1412: no baseline-metrics-report opt-in prompt remains — its data is
    now always git-tracked under data/ (see Phase 9), so the knob has
    nothing left to gate."""
    text = _text()
    assert not grep(r"[Bb]aseline-metrics report", text)
    assert not grep(r"baseline coverage and mutation metrics", text)
    assert not grep(r"7\.\s+\*\*Baseline-metrics report", text)


def test_phase_0_prompt_battery_ends_at_knob_6():
    """#1412: the numbered knob list stops at 6 — no dangling `7.` item."""
    text = _text()
    assert grep(r"^6\.\s+\*\*Code-lookup tools", text, ignore_case=True)
    assert not grep(r"^7\.\s+\*\*", text)


def test_phase_0_banner_no_longer_renders_report_on_off_segment():
    """#1412: the phase banner drops the `· report: <on|off>` segment
    entirely — its recap ends at `sink: <tracker|local>`."""
    text = _text()
    assert not grep(r"report:\s*<on\|off>", text)


def test_knob_6_remains_the_sole_enter_accepts_all_exception():
    """#1412: with knob 7 gone, knob 6 is still the sole exception to the
    Enter-accepts-all gesture — the "sole exception" wording survives."""
    text = _text()
    assert grep(r"sole.*exception|knob 6 is the \*\*sole\*\*", text, ignore_case=True)


def test_phase_0_persistence_no_longer_mentions_knob_7_outcome():
    """#1412: the Persistence paragraph no longer references a knob-7
    outcome — only the knob-6 (code-lookup) outcome remains."""
    text = _text()
    assert not grep(r"knob-7 outcome|baseline-metrics report was opted into", text)
    assert grep(r"knob-6 outcome", text)


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


def test_analyze_only_documents_the_bypass_carve_out_under_the_new_order():
    """#1422: --analyze-only still runs Phase 0 then Phase 1 directly and
    exits with no baseline captured — an intentional carve-out that bypasses
    the new default Baseline (Phase 2) / Derive Gherkin (Phase 3) ordering,
    not a contradiction of it."""
    text = _text()
    assert grep(r"bypass(ing|es)? the (new )?default[[:space:]]+Baseline", text, ignore_case=True)
    assert grep(r"No baseline is captured", text)


def test_phase_start_banner_requirement_documented_step_position_phase_n_with_settings_recap():
    """#1422: the banner format is `Step <position>/<total> — Phase <N>: <name>`,
    not the old bare `Phase N/9` — a bare counter would print
    non-monotonically (2/9, 3/9, 1/9) under the reordered execution
    sequence, reading as a hung/looping run. <total> is computed, not a
    literal 9 or 10, since Phase 7's participation isn't fixed."""
    text = _text()
    assert grep(r"Step <position>/<total> — Phase <N>", text)
    fence = _phase_start_banner_fence()
    # A bare-identity counter (e.g. `Phase <N>/9`, the pre-#1422 shape) must
    # not survive in the banner fence itself — anchored to the fence's own
    # content, not a substring match anywhere in the file, since the file
    # legitimately *mentions* that old shape in backticks while explaining
    # why it was replaced (a plain `not grep(r"^Phase N/9", text)` over the
    # whole file can never fail: the file never contained the literal string
    # "Phase N/9" un-templated in the first place).
    assert not re.search(r"^Phase <N>/\d", fence, re.MULTILINE)
    assert grep(r"mutation:.*binding:.*refactor:.*sink:", text, ignore_case=True)


def test_phase_start_banner_position_is_a_running_count_not_a_fixed_table():
    """#1422 (fixed post-build-review): <position> is a plain running count
    of phases printed so far — not a fixed per-identity lookup table. A
    fixed table (1=Phase 0, 2=Phase 2, ... 8=Phase 7-or-8, 9=Phase 9) was
    found to be unsatisfiable: Phase 7 and Phase 8 are not alternatives
    (both run, in sequence, when Phase 6 returns [y]), and a BDD-mode
    "none" run only executes 8 named phases, neither of which a fixed /9
    table can represent correctly."""
    text = _text()
    assert grep(
        r"running count of phases printed so far this run", text, ignore_case=True
    )
    assert not grep(r"7-or-8", text)


def test_phase_start_banner_total_is_computed_not_hardcoded():
    """#1422 (fixed post-build-review): <total> varies with two independent,
    known-at-different-times facts — BDD binding mode "none" (-1, known
    from Phase 0) and whether Phase 6 enters Phase 7 (+1, only known once
    Phase 6 resolves, since refactor-allowed mode doesn't guarantee [y] is
    chosen). The base count (Phase 7 excluded) is 9; entering Phase 7 makes
    it 10, announced with a one-line total-adjustment note."""
    text = _text()
    assert grep(r"[Bb]ase count is \*\*9\*\*", text)
    # Bound to the actual Phase 7/8 sequencing claim, not a stray two-word
    # phrase that any unrelated sentence elsewhere in the file could satisfy.
    assert grep_multiline(
        r"Phase 7 and Phase 8 are \*\*not alternatives\*\*.{0,120}"
        r"both Phase 7 \*and\* Phase 8 execute in sequence",
        text,
    )
    assert grep_multiline(
        r"Phase 7 entered.{0,40}total phase count.{0,40}now.{0,20}was",
        text,
    )
    # The other half of <total>'s arithmetic: -1 when BDD binding mode is
    # "none", known from Phase 0 onward (not just the +1/Phase-7 half).
    assert grep_multiline(
        r"\*\*-1\*\*.{0,60}Phase-0 BDD binding mode is `none`",
        text,
    )


def test_phase_0_answer_immutability_documented():
    text = _text()
    assert grep(r"immutable", text, ignore_case=True)
    assert grep(
        r"from-phase.*not.*re-prompt|not.*re-prompt.*from-phase|"
        r"delete.*phase-0\.md.*re-run",
        text,
        ignore_case=True,
    )


def test_phase_6_prompt_letter_is_y_b_q_not_r():
    assert grep(r"\[y\].*\[b\].*\[q\]|\[y/b/q\]", _text())
