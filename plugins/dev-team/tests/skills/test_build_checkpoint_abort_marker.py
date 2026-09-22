"""Content-guard test for skills/build/SKILL.md's abort-on-cheap-blocker
wiring (#2168, Step 1.2).

This is a prose-presence check only -- the actual redispatch/merge/no-pass-
without-redispatch behavior this prose describes is proven separately, by
Step 1.1's fixture equivalence test (tests/scripts/test_checkpoint_abort.py,
which exercises the real `merge_findings` function this prose names) and
`compute_round_outcome` unit tests. This file only proves the procedure text
instructing `/build` to follow that behavior is present, in both checkpoint
sub-steps, and names the correct function. Mirrors the established content-
guard style in tests/skills/test_code_review_synthesis_verbosity.py.
"""

from __future__ import annotations

from _repo_root import REPO_ROOT

SKILL = REPO_ROOT / "plugins" / "dev-team" / "skills" / "build" / "SKILL.md"

_STEP4_START = "- **complex**:"
_STEP4_END = "- If no complexity is specified"
_STEP6_START = "6. **Slice review checkpoint (batched).**"
_STEP6_END = "7. **Record review value"


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


def test_step4_complex_checkpoint_references_checkpoint_abort_script() -> None:
    section = _step4_section(_skill_text())
    assert "checkpoint_abort.py" in section, (
        "sub-step 4 (complex per-step checkpoint) must invoke "
        "checkpoint_abort.py before dispatching opus-tier lenses"
    )


def test_step4_complex_checkpoint_names_merge_findings() -> None:
    section = _step4_section(_skill_text())
    assert "checkpoint_abort.merge_findings(existing, new)" in section, (
        "sub-step 4 must name checkpoint_abort.merge_findings(existing, new) "
        "as the deferred-lens re-dispatch aggregation step"
    )


def test_step4_complex_checkpoint_uses_compute_round_outcome() -> None:
    section = _step4_section(_skill_text())
    assert "compute_round_outcome(aborted, redispatched, findings)" in section, (
        "sub-step 4's pass/blocked outcome must come from calling "
        "compute_round_outcome, not independently-reimplemented logic"
    )


def test_step6_slice_checkpoint_references_checkpoint_abort_script() -> None:
    section = _step6_section(_skill_text())
    assert "checkpoint_abort.py" in section, (
        "sub-step 6 (slice review checkpoint) must invoke checkpoint_abort.py "
        "before dispatching opus-tier lenses"
    )


def test_step6_slice_checkpoint_names_merge_findings() -> None:
    section = _step6_section(_skill_text())
    assert "checkpoint_abort.merge_findings(existing, new)" in section, (
        "sub-step 6 must name checkpoint_abort.merge_findings(existing, new) "
        "as the deferred-lens re-dispatch aggregation step"
    )


def test_step6_slice_checkpoint_uses_compute_round_outcome() -> None:
    section = _step6_section(_skill_text())
    assert "compute_round_outcome(aborted, redispatched, findings)" in section, (
        "sub-step 6's pass/blocked outcome must come from calling "
        "compute_round_outcome, not independently-reimplemented logic"
    )


def test_both_checkpoints_require_naming_deferred_lenses_and_trigger() -> None:
    text = _skill_text()
    for section in (_step4_section(text), _step6_section(text)):
        assert "name every deferred lens" in section, (
            "checkpoint report must name every deferred lens and the "
            "triggering finding (loud abort)"
        )
        assert "triggering finding" in section


def test_code_review_step4_non_support_sentence_is_stated() -> None:
    text = _skill_text()
    assert "dispatch_waves.py" in text
    assert "**not** ported there" in text, (
        "SKILL.md must state that /code-review step 4's parallel "
        "bounded-wave dispatch does not support this abort optimization"
    )
    assert "scoped to `/build`'s own checkpoints" in text
