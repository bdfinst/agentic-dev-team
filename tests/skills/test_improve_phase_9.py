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


def test_phase_9_no_longer_has_a_copy_report_data_step_or_guard_prompts():
    """Slice 4 Step 4.4 (plans/test-improve-baseline-persistence.md): there is
    nothing to copy or guard at Phase 9 anymore — baseline-coverage.json,
    baseline-mutation.json, and coverage-history.json are each written
    directly to tracked data/ at the point of capture (Phase 2 / Phase 5)."""
    s = _phase_9_section()
    assert not grep(r"[Cc]opy report data", s)
    assert not grep(r"existing-copy guard", s, ignore_case=True)
    assert not grep(r"keep/overwrite", s, ignore_case=True)


def test_phase_9_regeneratable_contract_describes_direct_write_durability():
    """Slice 4 Step 4.4: the regeneratable-from-tracked-data contract no
    longer branches on whether the .claude/memory/ working copy is present —
    data/ is always current by construction, so there is no copy step to
    re-run and no such branch to consider."""
    s = _phase_9_section()
    assert grep(r"already current by construction", s, ignore_case=True)
    assert not grep(r"memory-present|memory-absent", s, ignore_case=True)


def test_phase_9_names_mutation_history_as_outside_its_interpolation_set():
    """Slice 4 Step 4.4: mutation-history.json is not part of Phase 9's
    read/interpolation set — and never has been; it's consumed by
    /coverage-delta and /quality-targets-converge, not the executive-summary
    report."""
    s = _phase_9_section()
    assert grep(r"mutation-history\.json", s)
    assert grep(r"outside", s, ignore_case=True)


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


def test_phase_9_makes_no_memory_copy_present_or_absent_distinction():
    """Slice 4 Step 4.5 (plans/test-improve-baseline-persistence.md): the old
    "memory copy absent, read tracked directly" fallback branch no longer
    applies — the tracked file is unconditionally the only copy, so Phase 9's
    text makes no such distinction anywhere."""
    s = _phase_9_section()
    assert not grep(r"canonical copy is absent", s, ignore_case=True)
    assert not grep(r"skip the copy", s, ignore_case=True)


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


