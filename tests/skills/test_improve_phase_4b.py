"""Contract for /test-improve Phase 4b — refactor-decision prompt.

Issue #536, Slice 7.

Ported from tests/skills/test_improve_phase_4b_tests.bats (issue #674).
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, grep, section

SKILL = PLUGIN_ROOT / "skills" / "test-improve" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text()


def _phase_4b_section() -> str:
    return section(_text(), r"^### Phase 4b")


def test_body_contains_a_phase_4b_section_header():
    assert grep(r"^### Phase 4b", _text())


def test_phase_4b_shows_the_refactor_required_list_with_seam_behavior_risk_columns():
    s = _phase_4b_section()
    assert grep(r"seam", s, ignore_case=True)
    assert grep(r"behavior", s, ignore_case=True)
    assert grep(r"risk", s, ignore_case=True)


def test_phase_4b_prompt_uses_y_b_q():
    assert grep(r"\[y/b/q\]|\[y\].*\[b\].*\[q\]", _phase_4b_section())


def test_phase_4b_y_advances_to_phase_5():
    assert grep(
        r"\[y\].*Phase[[:space:]]+5|Phase[[:space:]]+5.*\[y\]",
        _phase_4b_section(),
        ignore_case=True,
    )


def test_phase_4b_b_writes_refactor_backlog_md_and_skips_to_phase_6():
    s = _phase_4b_section()
    assert grep(r"memory/test-improve/<slug>/refactor-backlog\.md", s)
    assert grep(
        r"\[b\].*(Phase[[:space:]]+6|skip)|skip.*Phase[[:space:]]+6.*\[b\]",
        s,
        ignore_case=True,
    )


def test_phase_4b_q_quits_before_phase_6():
    assert grep(
        r"\[q\].*(quit|no[[:space:]]+further|stop|exit)",
        _phase_4b_section(),
        ignore_case=True,
    )
