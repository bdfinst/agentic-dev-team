"""Contract for /test-improve Phase 6 threading --refactor-mode into
/quality-targets-converge, so the operator's no-refactor choice stays
enforced past Phase 4b.

Issue #968, Slice 1 Step 1.1.
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, grep, grep_multiline, section

SKILL = PLUGIN_ROOT / "skills" / "test-improve" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text()


def _phase_6_section() -> str:
    return section(_text(), r"^### Phase 6")


def test_phase_6_passes_refactor_mode_alongside_workflow_test_improve():
    s = _phase_6_section()
    assert grep(r"/quality-targets-converge.*--workflow[[:space:]]+test-improve", s)
    assert grep(r"--refactor-mode", s)


def test_phase_6_reads_refactor_mode_value_from_phase_0():
    assert grep_multiline(
        r"refactor-mode.*phase-0\.md|phase-0\.md.*refactor-mode",
        _phase_6_section(),
        ignore_case=True,
    )
