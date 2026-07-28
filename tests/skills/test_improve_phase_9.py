"""Contract for /test-improve Phase 9 — executive-summary report generation.

Issue #536, Slice 10 Step 10.2.

Ported from tests/skills/test_improve_phase_7_tests.bats (issue #674).
"""

from __future__ import annotations

from skill_doc_helpers import (
    PLUGIN_ROOT,
    grep,
    grep_multiline,
    phase_8_section,
    section,
)

SKILL = PLUGIN_ROOT / "skills" / "test-improve" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text()


def _phase_8_section() -> str:
    return phase_8_section(_text())


def _phase_9_section() -> str:
    return section(_text(), r"^### Phase 9")


def _close_out_section() -> str:
    return section(_text(), r"^### After Phase 9")


def test_body_contains_a_phase_9_section_header():
    assert grep(r"^### Phase 9", _text())


def test_phase_9_names_the_shipped_template_path():
    assert grep(
        r"plugins/dev-team/skills/test-improve/templates/executive-summary\.md",
        _phase_9_section(),
    )


def test_phase_9_names_the_output_path_shape():
    """#1412: the report lands at <slug>/report-<date>.md, paired with a
    <slug>/data/ sibling directory — the breaking rename from the old flat
    <repo-slug>-<date>.md path."""
    s = _phase_9_section()
    assert grep(r"\.dev-team-reports/test-improve/<slug>/report-<date>\.md", s)
    assert grep(r"\.dev-team-reports/test-improve/<slug>/data/", s)


def test_phase_9_test_counts_after_is_conditional_on_phase_8_having_run():
    """#1412: test-counts-after.json is copied into data/ only when Phase 8
    ran — absent when the operator quit before Phase 8 (e.g. after Phase 7)."""
    s = _phase_9_section()
    assert grep(r"test-counts-after\.json.{0,40}if Phase 8 ran", s)


def test_phase_9_documents_the_interpolation_rule():
    s = _phase_9_section()
    assert grep(r"interpolat|placeholder|substitut", s, ignore_case=True)
    assert grep(r"memory/test-improve/<slug>/", s)


def test_phase_9_documents_empty_section_not_applicable_rule():
    s = _phase_9_section()
    assert grep(r"not[[:space:]]+applicable", s, ignore_case=True)
    assert grep(
        r"(do[[:space:]]+not|never|not).*(disappear|hidden|omit)", s, ignore_case=True
    )


def test_phase_9_documents_parent_issue_post_or_feature_md_link_update():
    assert grep(
        r"parent[[:space:]]+issue|FEATURE\.md", _phase_9_section(), ignore_case=True
    )


def test_phase_9_documents_regeneratable_from_memory_contract():
    assert grep(
        r"regenerat|re-run.*Phase[[:space:]]+9|reproduce",
        _phase_9_section(),
        ignore_case=True,
    )


def test_phase_9_copies_baseline_and_history_artifacts_into_tracked_data():
    """#1412: Phase 9 unconditionally copies (never moves) baseline-coverage.json,
    baseline-mutation.json (baseline+kill-loop only), and coverage-history.json
    from their canonical .claude/memory/ working copy into the tracked data/
    sibling — no report opt-in gates this anymore."""
    s = _phase_9_section()
    assert grep(r"[Cc]opy report data", s)
    assert grep(r"unconditionally", s, ignore_case=True)
    assert grep(r"never[[:space:]]+move|never[[:space:]]+relocat", s, ignore_case=True)
    assert grep(r"baseline-coverage\.json", s)
    assert grep(r"baseline-mutation\.json", s)
    assert grep(r"coverage-history\.json", s)
    assert grep(r"data/", s)
    assert not grep(r"knob-7|report opt-in", s, ignore_case=True)


def test_phase_8_no_longer_branches_on_the_removed_report_opt_in():
    """#1412: Phase 8's branch-scoped-mutation-validation paragraph no longer
    conditions the whole-repo splice on a knob-7 opt-in — the splice source
    (Phase 2's unconditional, direct tracked-data/ baseline write) is always
    available regardless."""
    s = _phase_8_section()
    assert s, "Phase 8 section not found in test-improve/SKILL.md"
    assert not grep(r"knob-7|report opt-in", s, ignore_case=True)


def test_phase_8_whole_repo_splice_no_longer_describes_a_separate_phase_9_copy():
    """Slice 4 Step 4.3 (plans/test-improve-baseline-persistence.md): there is
    no longer a separate git-tracked data/ copy Phase 9 produces later — the
    tracked file Phase 2 wrote directly IS the only copy, so this paragraph
    no longer describes a deferred Phase-9 copy."""
    s = _phase_8_section()
    assert not grep(r"Phase 9 produces|produces later|Phase 9.*copy", s, ignore_case=True)


def test_phase_9_falls_back_to_reading_data_directly_when_memory_copy_is_absent():
    """#1412: when the canonical .claude/memory/ working copy is absent (e.g.
    a fresh checkout where only data/ was ever tracked), Phase 9 skips the
    copy and reads directly from data/'s already-present copies — this is
    the specific behavior the regeneratable-from-tracked-data contract
    depends on."""
    s = _phase_9_section()
    assert grep_multiline(
        r"absent.{0,200}skip[[:space:]]+the[[:space:]]+copy.{0,200}read[[:space:]]+directly",
        s,
        ignore_case=True,
    )


def test_phase_9_mutation_row_shape_covers_all_three_modes():
    """#1126: the Phase-9 mutation-row shape distinguishes `off` (not
    applicable), `kill-loop` (final-survivor, no baseline delta), and
    `baseline+kill-loop` (honest baseline-to-achieved score)."""
    s = _phase_9_section()
    # Bind each mode token to its row reading (bounded proximity) so the
    # mapping — not just token presence — is enforced.
    assert grep_multiline(r"`off`.{0,80}mutation disabled", s, ignore_case=True)
    assert grep_multiline(r"`kill-loop`.{0,120}final surviv", s, ignore_case=True)
    assert grep_multiline(r"`baseline\+kill-loop`.{0,120}(honest|baseline-to-achieved)", s, ignore_case=True)


# --- Post-Phase-9 re-run-with-refactor close-out prompt (issue #968) ----------


def test_close_out_section_header_exists():
    assert grep(r"^### After Phase 9", _text())


def test_close_out_prompt_uses_y_n_shape_and_names_backlog_count():
    s = _close_out_section()
    assert grep(r"\[y/n\]", s)
    assert grep(r"REFACTOR_REQUIRED", s)
    assert grep(r"remain[[:space:]]+backlogged", s, ignore_case=True)


def test_close_out_prompt_gated_on_backlog_file_and_phase_8_not_already_fired():
    s = _close_out_section()
    assert grep(r"refactor-backlog\.md", s)
    assert grep(r"coverage_reprompt_fired", s)


def test_close_out_prompt_suppressed_when_backlog_file_absent():
    s = _close_out_section()
    assert grep_multiline(
        r"no[[:space:]]+prompt.*does[[:space:]]+not[[:space:]]+exist",
        s,
        ignore_case=True,
    )


def test_close_out_prompt_suppressed_when_backlog_file_empty():
    s = _close_out_section()
    assert grep(r"zero[[:space:]]+entries", s, ignore_case=True)
    assert grep(r"no[[:space:]]+prompt", s, ignore_case=True)


def test_close_out_prompt_suppressed_when_phase_8_already_fired():
    s = _close_out_section()
    assert grep(
        r"coverage_reprompt_fired.*true.*no[[:space:]]+prompt|already[[:space:]]+fired",
        s,
        ignore_case=True,
    )


def test_phase_8_records_coverage_reprompt_fired_field():
    s = _phase_8_section()
    assert grep(r"coverage_reprompt_fired", s)


def test_close_out_prompt_suppressed_when_run_was_already_refactor_allowed():
    """A Phase-6 [b] backlog entry under refactor-allowed mode is a
    deliberate deferral, not a no-refactor constraint to lift — re-asking
    "re-run with refactor-allowed mode now?" would be nonsensical when
    that's the mode already in use (correctness-review, issue #968)."""
    s = _close_out_section()
    # Window widened from 400 (Slice 5 Step 5.9's refactor-backlog.md path
    # got longer: .dev-team-reports/test-improve/<slug>/refactor-backlog.md
    # vs the old bare refactor-backlog.md, pushing the gap past 400 chars).
    assert grep_multiline(
        r"no[[:space:]]+prompt.{0,500}refactor-allowed",
        s,
        ignore_case=True,
    )
    assert grep(r"refactor-mode:[[:space:]]+refactor-allowed", s)


def test_close_out_prompt_fires_only_when_run_was_no_refactor():
    s = _close_out_section()
    assert grep(r"refactor-mode:[[:space:]]+no-refactor", s)


# --- baseline-coverage.json / baseline-mutation.json existing-copy guard ----
# --- (issue #1412, Slice 2) -------------------------------------------------


def test_phase_9_baseline_coverage_prompts_with_keep_overwrite_default_keep():
    s = _phase_9_section()
    assert grep(r"baseline-coverage\.json", s)
    assert grep_multiline(
        r"overwrite it\s+\(recaptures the baseline every\s+downstream delta compares against\)",
        s,
    )
    assert grep_multiline(r"\[keep/overwrite,\s+default: keep\]", s)


def test_phase_9_declining_baseline_coverage_overwrite_keeps_existing_copy():
    s = _phase_9_section()
    assert grep_multiline(
        r"keep.{0,80}leaves the\s+existing `data/` copy in place",
        s,
        ignore_case=True,
    )
    assert grep_multiline(
        r"fresh capture is \*\*not\*\*\s+copied over it", s
    )


def test_phase_9_confirming_baseline_coverage_overwrite_replaces_data_copy():
    s = _phase_9_section()
    assert grep_multiline(
        r"overwrite.{0,40}replaces the\s+`data/` copy with the fresh",
        s,
        ignore_case=True,
    )


def test_phase_9_baseline_coverage_non_interactive_keeps_and_logs():
    s = _phase_9_section()
    assert grep_multiline(
        r"non-interactive.{0,40}\(no usable TTY /\s*`DEV_TEAM_AUTO_APPROVE=1`\)",
        s,
    )
    assert grep_multiline(
        r"keeps the\s+existing `data/` copy and logs the auto-decision",
        s,
    )
    assert grep(r"decision-defaults\.md", s)


def test_phase_9_baseline_mutation_non_interactive_keeps_and_logs():
    s = _phase_9_section()
    assert grep(r"baseline-mutation\.json", s)
    assert grep_multiline(
        r"overwrite it \(recaptures the mutation kill-rate baseline every\s+downstream\s+delta compares against\)",
        s,
    )
    assert grep_multiline(r"\[keep/overwrite,\s+default: keep\]", s)
    assert grep_multiline(
        r"non-interactive.{0,60}\(no usable TTY /\s*`DEV_TEAM_AUTO_APPROVE=1`\).{0,60}Phase 9",
        s,
    )
    assert grep_multiline(
        r"keeps the\s+existing `data/` copy and logs the auto-decision.{0,60}never",
        s,
    )


def test_phase_9_baseline_mutation_guard_declares_parity_with_coverage_guard():
    # #1412, Slice 2: baseline-mutation.json's guard is documented as the
    # identical keep/overwrite/unrecognized-answer discipline as
    # baseline-coverage.json's guard, not an independently-invented one —
    # this pins the cross-reference so the two never silently diverge.
    s = _phase_9_section()
    assert grep_multiline(
        r"identical guard applies to `baseline-mutation\.json`",
        s,
    )
    assert grep_multiline(
        r"[Ss]ame keep/overwrite/unrecognized-answer\s+behavior as"
        r"\s+`baseline-coverage\.json`'s guard above",
        s,
    )
