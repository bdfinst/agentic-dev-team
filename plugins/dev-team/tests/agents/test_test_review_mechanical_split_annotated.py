"""Mechanical-vs-judgment annotation check for test-review.md (#2169, plan
step 2.1 of plans/2164-abort-countable-tiered.md).

Step 2.1 is documentation-only: it annotates every existing check bullet
under ``## Detect`` and every bullet in the ``## Tolerated-Deviation Hunt``
section with ``[MECHANICAL]`` or ``[JUDGMENT]``, based on whether the
bullet's own text already states an explicit per-language detection
signature or grep/threshold rule. No detection behavior changes here (the
script that acts on the tags lands in Step 2.2) — this test only guards the
annotation itself: every check bullet carries exactly one tag, never zero,
never both.
"""

from __future__ import annotations

import re

import pytest

from _repo_root import REPO_ROOT

AGENT = REPO_ROOT / "plugins" / "dev-team" / "agents" / "test-review.md"

TAG_PATTERN = re.compile(r"\[(MECHANICAL|JUDGMENT)\]")
BULLET_START = re.compile(r"^- ")
CONTINUATION = re.compile(r"^[ \t]+\S")


def _text() -> str:
    return AGENT.read_text(encoding="utf-8")


def _section(text: str, start_heading: str, end_heading: str) -> str:
    start = text.index(start_heading) + len(start_heading)
    end = text.index(end_heading, start)
    return text[start:end]


def _bullet_blocks(section: str) -> list[str]:
    """Split a section into top-level ``- `` bullets, folding in indented
    continuation lines (this file wraps long bullets across multiple
    2-space-indented lines) but stopping at the next unindented line —
    a blank line, a new bullet, or a bare paragraph like
    ``**Consolidation rule** ...`` — so a bullet's trailing tag isn't
    accidentally absorbed into the next, untagged, non-bullet paragraph."""
    lines = section.split("\n")
    blocks: list[str] = []
    i, n = 0, len(lines)
    while i < n:
        if BULLET_START.match(lines[i]):
            block_lines = [lines[i]]
            j = i + 1
            while j < n and CONTINUATION.match(lines[j]):
                block_lines.append(lines[j])
                j += 1
            blocks.append("\n".join(block_lines))
            i = j
        else:
            i += 1
    return blocks


def _assert_each_bullet_has_exactly_one_tag(blocks: list[str]) -> None:
    untagged = [b.splitlines()[0] for b in blocks if not TAG_PATTERN.findall(b)]
    both = [
        b.splitlines()[0]
        for b in blocks
        if len(set(TAG_PATTERN.findall(b))) > 1
    ]
    assert not untagged, f"bullets missing [MECHANICAL]/[JUDGMENT] tag: {untagged}"
    assert not both, f"bullets carrying both tags: {both}"


def _block_containing(blocks: list[str], snippet: str) -> str:
    matches = [b for b in blocks if snippet in b]
    assert len(matches) == 1, f"expected exactly one bullet with {snippet!r}"
    return matches[0]


@pytest.fixture(scope="module")
def detect_section() -> str:
    text = _text()
    return _section(text, "## Detect", "## Tolerated-Deviation Hunt")


def test_detect_section_bullets_each_carry_exactly_one_tag(detect_section: str) -> None:
    blocks = _bullet_blocks(detect_section)
    assert len(blocks) >= 30, (
        f"expected the full set of ## Detect check bullets, found {len(blocks)}"
    )
    _assert_each_bullet_has_exactly_one_tag(blocks)


def test_tolerated_deviation_hunt_bullets_each_carry_exactly_one_tag() -> None:
    text = _text()
    section = _section(text, "## Tolerated-Deviation Hunt", "## Self-Challenge")
    blocks = _bullet_blocks(section)
    assert len(blocks) == 5, (
        f"expected the 5 tolerated-deviation-artifact categories, found {len(blocks)}"
    )
    _assert_each_bullet_has_exactly_one_tag(blocks)


def test_consolidation_rule_is_tagged_mechanical() -> None:
    text = _text()
    section = _section(text, "## Tolerated-Deviation Hunt", "## Self-Challenge")
    assert "**Consolidation rule** [MECHANICAL]:" in section, (
        "the >=3-artifact consolidation rule is an explicit threshold rule "
        "and should be tagged [MECHANICAL]"
    )


def test_testability_blockers_bullets_each_carry_exactly_one_tag(detect_section: str) -> None:
    """Testability blockers is a named subsection under ## Detect (not its
    own ## heading) — covered by the ## Detect sweep above, but pinned here
    directly per the task's explicit call-out of this section."""
    section = _section(detect_section, "Testability blockers:", "Internal-collaborator doubling")
    blocks = _bullet_blocks(section)
    assert len(blocks) == 3
    _assert_each_bullet_has_exactly_one_tag(blocks)


def test_internal_collaborator_doubling_bullets_each_carry_exactly_one_tag(
    detect_section: str,
) -> None:
    section = _section(
        detect_section,
        "Internal-collaborator doubling",
        "If a static-analysis pre-pass",
    )
    blocks = _bullet_blocks(section)
    assert len(blocks) == 3
    _assert_each_bullet_has_exactly_one_tag(blocks)
    # This subsection's own header already calls itself "mechanical — never
    # a truth judgment"; every bullet in it should agree with that framing.
    for block in blocks:
        assert "[MECHANICAL]" in block, (
            f"internal-collaborator-doubling bullet not tagged MECHANICAL: "
            f"{block.splitlines()[0]}"
        )


def test_reflection_bullet_is_mechanical_but_notes_non_gating_warning_severity(
    detect_section: str,
) -> None:
    """Reflection-into-private-members has an explicit per-language
    detection signature (MECHANICAL for detection) but must stay
    warning-severity and non-gating — only Step 2.2's no-assertion-tests
    check and internal_double_detector.py's error-severity findings gate
    the qualitative pass."""
    blocks = _bullet_blocks(detect_section)
    reflection_blocks = [
        b for b in blocks if "reflection into private members" in b
    ]
    assert len(reflection_blocks) == 1
    block = reflection_blocks[0]
    assert "[MECHANICAL]" in block
    assert "`warning`-severity" in block
    assert "without gating the qualitative pass" in block
    assert "Step 2.2" in block


@pytest.mark.parametrize(
    "snippet",
    [
        "Tests with no assertion",
        "Mocks/stubs not reset",
        "Missing await on async operations",
        "Unstubbed clock access",
        "Unstubbed randomness",
        "Unstubbed timers/delays",
    ],
)
def test_known_mechanical_anchor_bullets_are_tagged_mechanical(
    detect_section: str, snippet: str
) -> None:
    """Lock in the plan's explicit MECHANICAL examples (missing-await,
    mocks-not-reset, unstubbed clock/RNG/timers, tests-with-no-assertion)
    against accidental re-tagging."""
    blocks = _bullet_blocks(detect_section)
    assert "[MECHANICAL]" in _block_containing(blocks, snippet)


@pytest.mark.parametrize(
    "snippet",
    [
        "Missing edge cases",
        "No arrange-act-assert structure",
        "Misleading test descriptions",
        "Code under test that cannot be constructed with known values",
    ],
)
def test_known_judgment_anchor_bullets_are_tagged_judgment(
    detect_section: str, snippet: str
) -> None:
    """Lock in the plan's explicit JUDGMENT examples (coverage-gap
    adequacy, AAA structure, misleading descriptions, static-factory /
    singleton testability blockers) against accidental re-tagging."""
    blocks = _bullet_blocks(detect_section)
    assert "[JUDGMENT]" in _block_containing(blocks, snippet)


def test_assert_each_bullet_has_exactly_one_tag_raises_on_untagged_bullet() -> None:
    """Synthetic fixture exercises the untagged-bullet failure branch,
    which the live (already-compliant) test-review.md never triggers."""
    blocks = _bullet_blocks(
        "- Tagged bullet body. [MECHANICAL]\n- Untagged bullet body with no tag.\n"
    )
    with pytest.raises(AssertionError, match=r"missing \[MECHANICAL\]/\[JUDGMENT\] tag"):
        _assert_each_bullet_has_exactly_one_tag(blocks)


def test_assert_each_bullet_has_exactly_one_tag_raises_on_double_tagged_bullet() -> None:
    """Synthetic fixture exercises the double-tagged-bullet failure branch,
    which the live (already-compliant) test-review.md never triggers."""
    blocks = _bullet_blocks("- Double tagged bullet body. [MECHANICAL] [JUDGMENT]\n")
    with pytest.raises(AssertionError, match="bullets carrying both tags"):
        _assert_each_bullet_has_exactly_one_tag(blocks)
