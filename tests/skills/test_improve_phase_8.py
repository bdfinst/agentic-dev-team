"""Contract for /test-improve Phase 8 — validate via /quality-targets-converge.

Issue #536, Slice 9.

Ported from tests/skills/test_improve_phase_6_tests.bats (issue #674).
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, grep, grep_multiline, section

SKILL = PLUGIN_ROOT / "skills" / "test-improve" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text()


def _phase_8_section() -> str:
    return section(_text(), r"^### Phase 8")


def test_body_contains_a_phase_8_section_header():
    assert grep(r"^### Phase 8", _text())


def test_phase_8_invokes_quality_targets_converge_workflow_test_improve():
    assert grep(
        r"/quality-targets-converge.*--workflow[[:space:]]+test-improve",
        _phase_8_section(),
    )


def test_phase_8_mutation_target_is_skipped_not_waived_when_phase_0_disabled_mutation():
    assert grep(
        r"mutation.*(skip|not[[:space:]]+enabled).*not[[:space:]]+waiv|not[[:space:]]+waiv.*skip",
        _phase_8_section(),
        ignore_case=True,
    )


def test_phase_8_mutation_target_is_advisory_on_go():
    assert grep(r"Go.*advisory|advisory.*Go", _phase_8_section(), ignore_case=True)


def test_phase_8_mutation_target_reads_per_tristate_mode():
    """#1126: the Phase-8 mutation target reads `not enabled` for `off`,
    a final-survivor count for `kill-loop`, and a baseline delta for
    `baseline+kill-loop`."""
    s = _phase_8_section()
    # Bind each mode token to its own reading (bounded proximity) so a
    # scrambled mode→reading mapping cannot pass.
    assert grep_multiline(r"`off`.{0,160}not enabled", s, ignore_case=True)
    assert grep_multiline(r"`kill-loop`.{0,160}final[- ]surviv", s, ignore_case=True)
    assert grep_multiline(r"`baseline\+kill-loop`.{0,160}baseline[- ]delta|`baseline\+kill-loop`.{0,160}baseline-to-achieved", s, ignore_case=True)


def test_phase_8_surfaces_coverage_lt_90_re_run_prompt_with_y_n_shape():
    s = _phase_8_section()
    assert grep(r"coverage.*90|<[[:space:]]*90", s, ignore_case=True)
    assert grep(r"re-run|rerun", s, ignore_case=True)
    assert grep(r"\[y/n\]|\[y\].*\[n\]", s)


def test_phase_8_coverage_lt_90_prompt_lists_backlogged_refactor_required_items():
    assert grep(r"REFACTOR_REQUIRED|backlog", _phase_8_section(), ignore_case=True)
