"""Contract for /test-improve Phase 6 — refactor-decision prompt.

Issue #536, Slice 7.

Ported from tests/skills/test_improve_phase_4b_tests.bats (issue #674).
"""

from __future__ import annotations

from skill_doc_helpers import grep, section
from skill_include_resolver import resolve_test_improve_text as _text


def _phase_6_section() -> str:
    return section(_text(), r"^### Phase 6")


def test_body_contains_a_phase_6_section_header():
    assert grep(r"^### Phase 6", _text())


def test_phase_6_shows_the_refactor_required_list_with_seam_behavior_risk_columns():
    s = _phase_6_section()
    assert grep(r"seam", s, ignore_case=True)
    assert grep(r"behavior", s, ignore_case=True)
    assert grep(r"risk", s, ignore_case=True)


def test_phase_6_prompt_uses_y_b_q():
    assert grep(r"\[y/b/q\]|\[y\].*\[b\].*\[q\]", _phase_6_section())


def test_phase_6_y_advances_to_phase_7():
    assert grep(
        r"\[y\].*Phase[[:space:]]+7|Phase[[:space:]]+7.*\[y\]",
        _phase_6_section(),
        ignore_case=True,
    )


def test_phase_6_b_writes_refactor_backlog_md_and_skips_to_phase_8():
    s = _phase_6_section()
    assert grep(r"\.dev-team-reports/test-improve/<slug>/refactor-backlog\.md", s)
    assert grep(
        r"\[b\].*(Phase[[:space:]]+8|skip)|skip.*Phase[[:space:]]+8.*\[b\]",
        s,
        ignore_case=True,
    )


def test_phase_6_q_quits_before_phase_8():
    assert grep(
        r"\[q\].*(quit|no[[:space:]]+further|stop|exit)",
        _phase_6_section(),
        ignore_case=True,
    )
