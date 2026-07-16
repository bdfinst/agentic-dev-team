"""Contract for /test-improve Phase 7 — executive-summary report generation.

Issue #536, Slice 10 Step 10.2.

Ported from tests/skills/test_improve_phase_7_tests.bats (issue #674).
"""

from __future__ import annotations

from skill_doc_helpers import (
    PLUGIN_ROOT,
    grep,
    grep_multiline,
    section,
    phase_6_section,
)

SKILL = PLUGIN_ROOT / "skills" / "test-improve" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text()


def _phase_6_section() -> str:
    return phase_6_section(_text())


def _phase_7_section() -> str:
    return section(_text(), r"^### Phase 7")


def _close_out_section() -> str:
    return section(_text(), r"^### After Phase 7")


def test_body_contains_a_phase_7_section_header():
    assert grep(r"^### Phase 7", _text())


def test_phase_7_names_the_shipped_template_path():
    assert grep(
        r"plugins/dev-team/skills/test-improve/templates/executive-summary\.md",
        _phase_7_section(),
    )


def test_phase_7_names_the_output_path_shape():
    s = _phase_7_section()
    assert grep(r"reports/test-improve/", s)
    assert grep(r"<repo-slug>|<slug>", s, ignore_case=True)


def test_phase_7_documents_the_interpolation_rule():
    s = _phase_7_section()
    assert grep(r"interpolat|placeholder|substitut", s, ignore_case=True)
    assert grep(r"memory/test-improve/<slug>/", s)


def test_phase_7_documents_empty_section_not_applicable_rule():
    s = _phase_7_section()
    assert grep(r"not[[:space:]]+applicable", s, ignore_case=True)
    assert grep(
        r"(do[[:space:]]+not|never|not).*(disappear|hidden|omit)", s, ignore_case=True
    )


def test_phase_7_documents_parent_issue_post_or_feature_md_link_update():
    assert grep(
        r"parent[[:space:]]+issue|FEATURE\.md", _phase_7_section(), ignore_case=True
    )


def test_phase_7_documents_regeneratable_from_memory_contract():
    assert grep(
        r"regenerat|re-run.*Phase[[:space:]]+7|reproduce",
        _phase_7_section(),
        ignore_case=True,
    )


def test_phase_7_interpolation_resolves_baselines_via_the_phase_2_write_path():
    """#1126: Phase 7 resolves baseline artifacts from the knob-7 write path
    that Phase 2 owns (single source of truth), rather than re-deriving the
    reports-vs-memory branch here."""
    s = _phase_7_section()
    assert grep(r"knob-7", s, ignore_case=True)
    assert grep(r"Phase 2", s)
    assert grep(r"baseline artifacts|baseline-coverage\.json", s, ignore_case=True)


def test_phase_7_mutation_row_shape_covers_all_three_modes():
    """#1126: the Phase-7 mutation-row shape distinguishes `off` (not
    applicable), `kill-loop` (final-survivor, no baseline delta), and
    `baseline+kill-loop` (honest baseline-to-achieved score)."""
    s = _phase_7_section()
    # Bind each mode token to its row reading (bounded proximity) so the
    # mapping — not just token presence — is enforced.
    assert grep_multiline(r"`off`.{0,80}mutation disabled", s, ignore_case=True)
    assert grep_multiline(r"`kill-loop`.{0,120}final surviv", s, ignore_case=True)
    assert grep_multiline(r"`baseline\+kill-loop`.{0,120}(honest|baseline-to-achieved)", s, ignore_case=True)


# --- Post-Phase-7 re-run-with-refactor close-out prompt (issue #968) ----------


def test_close_out_section_header_exists():
    assert grep(r"^### After Phase 7", _text())


def test_close_out_prompt_uses_y_n_shape_and_names_backlog_count():
    s = _close_out_section()
    assert grep(r"\[y/n\]", s)
    assert grep(r"REFACTOR_REQUIRED", s)
    assert grep(r"remain[[:space:]]+backlogged", s, ignore_case=True)


def test_close_out_prompt_gated_on_backlog_file_and_phase_6_not_already_fired():
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


def test_close_out_prompt_suppressed_when_phase_6_already_fired():
    s = _close_out_section()
    assert grep(
        r"coverage_reprompt_fired.*true.*no[[:space:]]+prompt|already[[:space:]]+fired",
        s,
        ignore_case=True,
    )


def test_phase_6_records_coverage_reprompt_fired_field():
    s = _phase_6_section()
    assert grep(r"coverage_reprompt_fired", s)


def test_close_out_prompt_suppressed_when_run_was_already_refactor_allowed():
    """A Phase-4b [b] backlog entry under refactor-allowed mode is a
    deliberate deferral, not a no-refactor constraint to lift — re-asking
    "re-run with refactor-allowed mode now?" would be nonsensical when
    that's the mode already in use (correctness-review, issue #968)."""
    s = _close_out_section()
    assert grep_multiline(
        r"no[[:space:]]+prompt.{0,400}refactor-allowed",
        s,
        ignore_case=True,
    )
    assert grep(r"refactor-mode:[[:space:]]+refactor-allowed", s)


def test_close_out_prompt_fires_only_when_run_was_no_refactor():
    s = _close_out_section()
    assert grep(r"refactor-mode:[[:space:]]+no-refactor", s)
