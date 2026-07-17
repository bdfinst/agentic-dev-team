"""Contract for /test-improve's `--from-phase` no-argument auto-detect form
(issue #1151).

The deterministic scan/ordering lives in
`scripts/test_improve_resume.py` (unit-tested under the plugin's own
tests/scripts tree); these assertions verify the SKILL.md wires that helper
in and documents the optional-number form, the 4b ordering, the error
behavior, and the explicit-override semantics.
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, collapsed, grep

SKILL = PLUGIN_ROOT / "skills" / "test-improve" / "SKILL.md"
HELPER = PLUGIN_ROOT / "scripts" / "test_improve_resume.py"


def _text() -> str:
    return SKILL.read_text()


def test_helper_script_ships():
    assert HELPER.is_file()


def test_argument_hint_marks_number_optional():
    # `[<n>]` inside the argument-hint signals the number is optional.
    assert grep(r"--from-phase \[<n>\]", _text())


def test_from_phase_bullet_documents_no_arg_autodetect():
    body = collapsed(_text())
    assert "auto-detect" in body.lower()
    assert "number is optional" in body.lower()


def test_skill_invokes_the_resume_helper():
    body = collapsed(_text())
    assert "scripts/test_improve_resume.py" in body


def test_skill_documents_4b_ordering_resolution():
    body = collapsed(_text())
    # phase-4 with no 4b -> Phase 4b; phase-4b completed -> Phase 6.
    assert grep(r"phase-4b", body)
    assert "skip-to-6" in body


def test_skill_documents_error_when_no_phase_files():
    body = collapsed(_text()).lower()
    assert "do **not** silently start at" in _text().lower() or "not silently start" in body
    assert "from phase 0" in body


def test_skill_documents_explicit_override():
    body = collapsed(_text())
    assert "--explicit" in body
    assert grep(r"explicit `<n>` \*\*overrides\*\*", body)


def test_handoff_hints_mention_autodetect_form():
    # All four resume hints (Phases 1, 4, 5, 6) gain the no-arg mention.
    text = _text()
    hint_lines = [
        line
        for line in text.splitlines()
        if "To resume: /test-improve" in line
    ]
    assert len(hint_lines) == 4
    for line in hint_lines:
        assert "--from-phase with no number to auto-detect" in line
