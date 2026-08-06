"""Contract for /test-improve Phase 8 threading --refactor-mode into
/quality-targets-converge, so the operator's no-refactor choice stays
enforced past Phase 6.

Issue #968, Slice 1 Step 1.1.
"""

from __future__ import annotations

from skill_doc_helpers import grep, grep_multiline, phase_8_section
from skill_include_resolver import resolve_test_improve_text as _text


def _phase_8_section() -> str:
    return phase_8_section(_text())


def test_phase_8_passes_refactor_mode_alongside_workflow_test_improve():
    """Combined, same-invocation-line check — two independent asserts would
    only prove both tokens exist somewhere in Phase 8, not that
    --refactor-mode is threaded onto the same /quality-targets-converge
    dispatch as --workflow (test-review, issue #968)."""
    s = _phase_8_section()
    assert grep(
        r"/quality-targets-converge.*--workflow[[:space:]]+test-improve.*--refactor-mode",
        s,
    )


def test_phase_8_reads_refactor_mode_value_from_phase_0():
    """Bounded proximity (not unbounded DOTALL) so the assert fails if the
    phrasing linking --refactor-mode to phase-0.md drifts apart in a future
    edit (test-review, issue #968)."""
    assert grep_multiline(
        r"--refactor-mode.{0,120}phase-0\.md|phase-0\.md.{0,120}--refactor-mode",
        _phase_8_section(),
        ignore_case=True,
    )
