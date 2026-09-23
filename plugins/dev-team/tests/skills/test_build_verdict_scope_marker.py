"""Content-guard test for skills/build/SKILL.md's ledger-scoped dispatch
wiring (#2167).

This is a prose-presence check only -- the actual skip/fail-closed
behavior this prose describes is proven separately by
`tests/scripts/test_verdict_scope.py`. This file only proves the procedure
text instructing `/build`'s checkpoints to emit the scope marker and consult
the ledger is present in both checkpoint sub-steps, and that the shared
block explains why that closes Step 6's backstop-scoping gap without
Step-6-specific code. Mirrors `test_build_checkpoint_abort_marker.py`'s
established style for this same file's other shared-block rules.
"""

from __future__ import annotations

from _repo_root import REPO_ROOT

SKILL = REPO_ROOT / "plugins" / "dev-team" / "skills" / "build" / "SKILL.md"

_STEP4_START = "- **complex**:"
_STEP4_END = "- If no complexity is specified"
_STEP6_START = "6. **Slice review checkpoint (batched).**"
_STEP6_END = "7. **Record review value"
_SHARED_START = (
    "**Ledger-scoped dispatch (#2167) — applies to both checkpoint fix loops "
    "above (sub-steps 4 and 6).**"
)
_SHARED_END = "**Verification-mode re-dispatch (#1628)"


def _skill_text() -> str:
    return SKILL.read_text(encoding="utf-8")


def _section(text: str, start: str, end: str) -> str:
    assert start in text, f"marker not found: {start!r}"
    after_start = text.split(start, 1)[1]
    assert end in after_start, f"marker not found: {end!r}"
    return after_start.split(end, 1)[0]


def _step4_section(text: str) -> str:
    return _section(text, _STEP4_START, _STEP4_END)


def _step6_section(text: str) -> str:
    return _section(text, _STEP6_START, _STEP6_END)


def _shared_section(text: str) -> str:
    return _section(text, _SHARED_START, _SHARED_END)


def test_step4_points_to_shared_ledger_scoped_dispatch_rule() -> None:
    section = _step4_section(_skill_text())
    assert "Ledger-scoped dispatch (#2167)" in section


def test_step6_points_to_shared_ledger_scoped_dispatch_rule() -> None:
    section = _step6_section(_skill_text())
    assert "Ledger-scoped dispatch (#2167)" in section


def test_ledger_scoped_dispatch_rule_is_stated_once_in_a_shared_block() -> None:
    text = _skill_text()
    assert text.count(_SHARED_START) == 1, (
        "the Ledger-scoped dispatch (#2167) rule must be stated exactly "
        "once, in a shared block scoped to both checkpoint fix loops"
    )


def test_shared_block_requires_the_scope_marker() -> None:
    section = _shared_section(_skill_text())
    assert "Files in scope for this review:" in section
    assert "SCOPE_MARKER_PREFIX" in section
    assert "review_verdict_recorder.py" in section


def test_shared_block_names_verdict_scope_script_and_outputs() -> None:
    section = _shared_section(_skill_text())
    assert "verdict_scope.py" in section
    assert "toDispatch" in section
    assert "fullySkippedLenses" in section


def test_shared_block_explains_backstop_scoping_needs_no_new_code() -> None:
    section = _shared_section(_skill_text())
    assert "Step 6" in section
    assert "no Step-6-specific code" in section or "no separate Step 6-specific logic" in section


def test_shared_block_states_backstop_review_skip_flag_is_unaffected() -> None:
    section = _shared_section(_skill_text())
    assert "--backstop-review=skip" in section
