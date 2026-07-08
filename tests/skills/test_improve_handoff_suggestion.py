"""Contract for /test-improve's /handoff suggestion at context-heavy phase
boundaries (Phase 1, Phase 4's review loop, Phase 5's review loop, Phase 6)
— and its explicit absence at the lighter gates (Phase 2b, Phase 3, Phase 4b).

Issue #968, Slice 1 Step 1.3.
"""

from __future__ import annotations

import re

from skill_doc_helpers import PLUGIN_ROOT, grep, section

SKILL = PLUGIN_ROOT / "skills" / "test-improve" / "SKILL.md"

SUGGESTION_LINE_1 = r"Consider running /handoff to compress context"
SUGGESTION_LINE_2 = r"--from-phase"


def _text() -> str:
    return SKILL.read_text()


def _phase_1_section() -> str:
    return section(_text(), r"^### Phase 1")


def _phase_2b_section() -> str:
    return section(_text(), r"^### Phase 2b")


def _phase_3_section() -> str:
    return section(_text(), r"^### Phase 3( —|$| \()")


def _phase_4_section() -> str:
    return section(_text(), r"^### Phase 4( —|$| \()")


def _phase_4b_section() -> str:
    return section(_text(), r"^### Phase 4b")


def _phase_5_section() -> str:
    return section(_text(), r"^### Phase 5")


def _phase_6_section() -> str:
    return section(_text(), r"^### Phase 6")


def _has_suggestion(s: str) -> bool:
    # The suggestion prose wraps across physical lines (even mid-phrase), so
    # collapse all whitespace to single spaces before checking for the two
    # required substrings — a literal multi-line match would miss a phrase
    # split across a line break.
    collapsed = " ".join(s.split())
    return grep(SUGGESTION_LINE_1, collapsed) and grep(SUGGESTION_LINE_2, collapsed)


def test_handoff_suggestion_present_after_phase_1():
    assert _has_suggestion(_phase_1_section())


def test_handoff_suggestion_present_in_phase_4_review_loop():
    assert _has_suggestion(_phase_4_section())


def test_handoff_suggestion_present_in_phase_5_review_loop():
    assert _has_suggestion(_phase_5_section())


def test_handoff_suggestion_present_after_phase_6():
    assert _has_suggestion(_phase_6_section())


def test_handoff_suggestion_absent_from_phase_2b():
    assert not _has_suggestion(_phase_2b_section())


def test_handoff_suggestion_absent_from_phase_3():
    assert not _has_suggestion(_phase_3_section())


def test_handoff_suggestion_absent_from_phase_4b():
    assert not _has_suggestion(_phase_4b_section())


_MESSAGE_RE = re.compile(r"Phase \S+ complete\..{0,300}?--from-phase \S+", re.DOTALL)


def test_suggestion_wording_is_identical_at_all_four_insertion_points_modulo_phase_number():
    """The "Phase N complete." prefix and the trailing --from-phase target
    legitimately vary per insertion point — only those two tokens should
    differ, not the rest of the wording. Whitespace is normalized first
    since the prose wraps across physical lines."""
    sections = [
        _phase_1_section(),
        _phase_4_section(),
        _phase_5_section(),
        _phase_6_section(),
    ]
    variants = set()
    for s in sections:
        collapsed = " ".join(s.split())
        match = _MESSAGE_RE.search(collapsed)
        assert match, f"no suggestion message found in section: {collapsed[:200]}"
        normalized = re.sub(
            r"Phase \S+ complete\.", "Phase N complete.", match.group(0)
        )
        normalized = re.sub(r"--from-phase \S+", "--from-phase N", normalized)
        variants.add(normalized)
    assert len(variants) == 1
