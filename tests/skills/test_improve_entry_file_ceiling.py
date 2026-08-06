"""Regression tests for /test-improve's entry-file size and no-inline-content
invariants (plan: test-improve-context-loading-strategy, Slice 1, Step 1.13).

Steps 1.4-1.12 extracted all ten phases (0-9) plus the Phase-9 close-out
prompt out of `skills/test-improve/SKILL.md` into `references/*.md` files,
splicing each back in via a `<!-- include: ... -->` marker. Slice 1's
Acceptance critic found nothing that would catch a *future* edit re-growing
the entry file back toward its pre-split size, or drifting the two
`references/*.md` files a shared trigger-condition sentence in the entry
file's own prose depends on — this module closes both gaps, plus the
fixed token-count ceiling from Step 1.13 assertion 1.

Deliberately self-contained within Slice 1: uses `_approx_tokens()` (a
plain char-count/4 heuristic, promoted to `skill_doc_helpers.py`) rather
than importing Slice 2's not-yet-created `scripts/measure_tokens.py`
(Wave 2, doesn't exist when Slice 1 runs in Wave 1). Slice 2 Step 2.1's
`tests/scripts/test_measure_tokens.py` separately covers that module's own
correctness — this file only guards the entry file's size.
"""

from __future__ import annotations

import re

from skill_doc_helpers import _approx_tokens
from skill_include_resolver import INCLUDE_RE, SKILL, SKILL_DIR

# Pre-split baseline was ~16,500 tokens (measured before Step 1.1). The plan's
# placeholder ceiling — 30% of that baseline, ~4,950 tokens — would pass
# trivially here: post-split SKILL.md measures ~2,973 tokens (11,894 chars),
# already 40% under the placeholder, because all ten phases were extracted in
# Steps 1.4-1.12 rather than just some of them. A ceiling that never comes
# close to binding wouldn't catch the regression it exists to catch, so this
# pins a tighter bar instead: ~18% of headroom over the current measured
# size (3,500 tokens / 14,000 chars) — enough for incidental prose growth
# (a new table row, a clarifying sentence) but not enough for a phase's
# procedural detail to silently move back inline.
_ENTRY_FILE_TOKEN_CEILING = 3500

# Max observed today is 5 non-blank lines (Phases 1, 5, 7, 8, 9: an include
# marker plus up to 4 lines of wrapped pointer prose). A ceiling of 5 leaves
# zero headroom — 5 of 11 sections already sit exactly at it, so a purely
# cosmetic edit (a clarifying word that reflows a pointer sentence onto a
# 6th line) would trip this test while nothing actually moved back inline.
# 7 keeps real regressions caught (a re-inlined phase runs dozens of lines)
# while tolerating incidental reflow.
_PHASE_HEADING_RE = re.compile(r"^### (Phase \d+.*|After Phase 9.*)$", re.MULTILINE)
_BODY_LINE_CEILING = 7


def _skill_text() -> str:
    return SKILL.read_text(encoding="utf-8")


def test_entry_file_is_below_the_token_ceiling():
    """Guards the 70%-reduction goal mechanically: a future edit that moves
    a phase's procedural detail back inline (or otherwise re-grows the
    entry file) fails this test instead of relying on a one-time manual
    read of the file."""
    tokens = _approx_tokens(_skill_text())
    assert tokens < _ENTRY_FILE_TOKEN_CEILING, (
        f"skills/test-improve/SKILL.md measures ~{tokens} approx-tokens — "
        f"at or above the {_ENTRY_FILE_TOKEN_CEILING}-token ceiling. Move "
        f"the added content into a references/*.md file instead of leaving "
        f"it inline."
    )


def _phase_and_after_sections() -> list[tuple[str, str]]:
    """Every `### Phase N` heading, plus the trailing `### After Phase 9`
    heading, paired with the raw body text between it and the next such
    heading (or end of file for the last one). Operates on SKILL.md's raw
    text directly — never the include-resolved combined text — so this
    test fails the moment a phase's body stops being a short pointer plus
    an include marker."""
    text = _skill_text()
    matches = list(_PHASE_HEADING_RE.finditer(text))
    sections = []
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections.append((match.group(0), text[start:end]))
    return sections


def test_every_phase_section_and_after_phase_9_are_short_pointers_with_include_markers():
    sections = _phase_and_after_sections()

    # Ten numbered phases (0-9) plus the "After Phase 9" close-out section.
    assert len(sections) == 11, (
        f"expected 11 sections (Phase 0-9 + After Phase 9), found "
        f"{len(sections)}: {[heading for heading, _ in sections]}"
    )

    for heading, body in sections:
        content_lines = [line for line in body.splitlines() if line.strip()]
        assert len(content_lines) <= _BODY_LINE_CEILING, (
            f"{heading!r} body has {len(content_lines)} non-blank lines "
            f"(ceiling {_BODY_LINE_CEILING}) — its procedural detail "
            f"belongs in a references/*.md file, not inline:\n{body}"
        )
        assert INCLUDE_RE.search(body), (
            f"{heading!r} body has no <!-- include: references/*.md --> "
            f"marker — its content has not been extracted:\n{body}"
        )


def test_bdd_binding_mode_none_trigger_condition_is_consistent_with_phase_3():
    """The Phase-start banner's `<total>`-computation prose names the
    trigger condition for skipping Phase 3 ('the Phase-0 BDD binding mode
    is `none`'). That condition's actual behavior lives entirely in
    references/phase-3-derive-gherkin.md — assert both still agree on the
    keywords, so an edit to one without the other fails this test instead
    of drifting silently."""
    skill_text = _skill_text()
    assert "BDD binding mode is `none`" in skill_text

    phase_3_text = (SKILL_DIR / "references" / "phase-3-derive-gherkin.md").read_text(
        encoding="utf-8"
    )
    assert re.search(r"binding mode", phase_3_text, re.IGNORECASE), (
        "references/phase-3-derive-gherkin.md no longer mentions 'binding "
        "mode' — SKILL.md's banner prose names this as Phase 3's skip "
        "trigger and now has nothing to point at"
    )
    assert "`none`" in phase_3_text, (
        "references/phase-3-derive-gherkin.md no longer names binding mode "
        "`none` — SKILL.md's banner prose names this as Phase 3's skip "
        "trigger and now has nothing to point at"
    )


def test_phase_6_resolves_to_y_trigger_condition_is_consistent_with_phase_6():
    """Same cross-file consistency check as above, for the banner's other
    trigger condition: entering Phase 7 the moment 'Phase 6 resolves to
    `[y]`'. That decision lives entirely in
    references/phase-6-refactor-decision.md."""
    skill_text = _skill_text()
    assert "Phase 6 resolves to `[y]`" in skill_text

    phase_6_text = (
        SKILL_DIR / "references" / "phase-6-refactor-decision.md"
    ).read_text(encoding="utf-8")
    assert "`[y]`" in phase_6_text, (
        "references/phase-6-refactor-decision.md no longer names the `[y]` "
        "decision letter — SKILL.md's banner prose names this as the "
        "Phase-7-entry trigger and now has nothing to point at"
    )
    assert "Phase 7" in phase_6_text, (
        "references/phase-6-refactor-decision.md no longer mentions "
        "Phase 7 — SKILL.md's banner prose names entering Phase 7 as the "
        "consequence of the `[y]` decision and now has nothing to point at"
    )
