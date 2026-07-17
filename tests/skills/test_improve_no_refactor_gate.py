"""Contract for /test-improve's no-refactor mode gate at Phase 4b / Phase 5.

Issue #1146: with `refactor-mode: no-refactor` (the Phase-0 default),
Phase 4b must be informational — it must NOT offer `[y] enter Phase 5` — and
Phase 5 must hard-refuse to run. Refactor-requiring items surface as
out-of-scope, never as actionable Stories.

These are structural sensors over the shipped SKILL.md prose.
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, collapsed, grep, section

SKILL = PLUGIN_ROOT / "skills" / "test-improve" / "SKILL.md"
IFA_SKILL = PLUGIN_ROOT / "skills" / "issues-from-assessment" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text()


def _phase_4b_section() -> str:
    return section(_text(), r"^### Phase 4b")


def _phase_5_section() -> str:
    return section(_text(), r"^### Phase 5")


def _phase_3_section() -> str:
    return section(_text(), r"^### Phase 3")


def _phase_1_section() -> str:
    return section(_text(), r"^### Phase 1")


def _no_refactor_block() -> str:
    """The Phase-4b sub-block that governs `refactor-mode: no-refactor`,
    isolated from the `refactor-allowed` sub-block that follows it."""
    s = _phase_4b_section()
    start = s.index("refactor-mode: no-refactor")
    end = s.index("refactor-mode: refactor-allowed")
    assert start < end, "Phase 4b must document no-refactor before refactor-allowed"
    return s[start:end]


def _refactor_allowed_block() -> str:
    s = _phase_4b_section()
    return s[s.index("refactor-mode: refactor-allowed"):]


# --- Phase 4b: no-refactor mode removes [y] enter Phase 5 --------------------


def test_phase_4b_branches_on_refactor_mode_read_from_phase_0():
    s = _phase_4b_section()
    assert grep(r"refactor-mode", s)
    assert grep(r"phase-0\.md", s)


def test_phase_4b_no_refactor_explicitly_removes_y_enter_phase_5():
    """In no-refactor mode the `[y] enter Phase 5` option is stated to not
    exist — the operator is never offered the refactor branch."""
    block = collapsed(_no_refactor_block())
    assert grep(r"enter Phase 5", block)
    assert grep(r"does not exist", block, ignore_case=True)


def test_phase_4b_no_refactor_omits_the_actionable_y_b_q_prompt():
    """The full `[y/b/q]` decision prompt appears ONLY in the refactor-allowed
    branch — the no-refactor branch must not present it."""
    assert "[y/b/q]" not in _no_refactor_block()
    assert "[y/b/q]" in _refactor_allowed_block()


def test_phase_4b_no_refactor_is_informational_and_auto_backlogs():
    block = _no_refactor_block()
    assert grep(r"informational", block, ignore_case=True)
    assert grep(r"out of scope", block, ignore_case=True)
    assert grep(r"auto-backlog", block, ignore_case=True)
    assert grep(r"refactor-backlog\.md", block)
    assert grep(r"Phase 6", block)


def test_phase_4b_refactor_allowed_keeps_full_y_b_q_prompt():
    block = _refactor_allowed_block()
    assert grep(r"\[y/b/q\]", block)
    assert grep(r"\[y\].*enter.*Phase 5|Phase 5.*\[y\]", block, ignore_case=True)
    assert grep(r"\[b\]", block)
    assert grep(r"\[q\]", block)


# --- Phase 5: hard mode gate -------------------------------------------------


def test_phase_5_hard_gates_on_no_refactor_mode():
    s = _phase_5_section()
    assert grep(r"refuses to run", s, ignore_case=True)
    assert grep(r"no-refactor", s)


def test_phase_5_refuses_even_if_y_is_reached():
    s = _phase_5_section()
    assert grep(r"even if.*\[y\]|\[y\].*somehow", s, ignore_case=True)


def test_phase_5_rereads_refactor_mode_from_phase_0():
    s = collapsed(_phase_5_section())
    assert grep(r"refactor-mode.{0,80}phase-0\.md|phase-0\.md.{0,80}refactor-mode", s)


# --- Refactor-requiring items are out-of-scope, never actionable Stories -----


def test_phase_3_defers_refactor_required_and_never_writes_them_as_stories():
    s = _phase_3_section()
    assert grep(r"REFACTOR_REQUIRED", s)
    assert grep(r"not written as Phase-4 Stories", s)


def test_phase_3_labels_refactor_required_out_of_scope_in_no_refactor():
    s = _phase_3_section()
    assert grep(r"out-of-scope|out of scope", s, ignore_case=True)
    assert grep(r"skipped-in-no-refactor", s)


def test_phase_3_threads_refactor_mode_into_issues_from_assessment():
    s = _phase_3_section()
    assert grep(r"/issues-from-assessment.*--refactor-mode", s)


def test_phase_1_plan_labels_refactor_items_skipped_in_no_refactor():
    s = _phase_1_section()
    assert grep(r"skipped-in-no-refactor", s)
    assert grep(r"never presented as ordinary next steps|out of scope", s, ignore_case=True)


# --- issues-from-assessment honors --refactor-mode ---------------------------


def test_issues_from_assessment_accepts_refactor_mode_flag():
    t = IFA_SKILL.read_text()
    assert grep(r"^argument-hint:.*--refactor-mode", t)
    assert grep(r"--refactor-mode", t)


def test_issues_from_assessment_no_refactor_marks_refactor_work_out_of_scope():
    t = IFA_SKILL.read_text()
    assert grep(r"out-of-scope|out of scope", t, ignore_case=True)
    assert grep(r"skipped-in-no-refactor", t)
    assert grep(r"never.*actionable Stories|not created as actionable Stories", t, ignore_case=True)
