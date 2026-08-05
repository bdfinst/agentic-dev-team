"""Structural guard for Step 1.9 and Step 1.10 of
plans/test-improve-context-loading-strategy.md (Slice 1): the end-of-phase
review loop and its fixed evidence schema must be extracted exactly once
into references/review-loop.md and genuinely *shared* via an include marker
— never duplicated into phase-5-improve.md or phase-7-refactor.md alongside
a decorative marker.

Two positive clauses (the shared file exists exactly once; each of
phase-5-improve.md and phase-7-refactor.md names it via an include marker)
and one negative clause per file (with the marker line and its paired
human-readable pointer sentence stripped out, the file's own remaining raw
text contains none of the evidence-schema field names or other distinctive
review-loop prose) — the negative clause is what a decorative-but-unused
marker (marker present, content duplicated anyway) can't fake a pass on.
"""

from __future__ import annotations

import pytest
from skill_include_resolver import INCLUDE_RE, SKILL_DIR

PHASE_5_IMPROVE = SKILL_DIR / "references" / "phase-5-improve.md"
PHASE_7_REFACTOR = SKILL_DIR / "references" / "phase-7-refactor.md"
REVIEW_LOOP_INCLUDING_FILES = [PHASE_5_IMPROVE, PHASE_7_REFACTOR]
REVIEW_LOOP_INCLUDE_MARKER = "<!-- include: references/review-loop.md -->"

# The fixed evidence-schema fields (Step 1.9's plan text, verbatim).
EVIDENCE_SCHEMA_FIELDS = [
    "base_sha",
    "head_sha",
    "farley_score",
    "smells",
    "code_review",
    "iterations",
    "escalated",
]

# Distinctive review-loop prose that only genuinely lives in review-loop.md
# (not in either including file's own pointer sentence — each entry is
# checked against review-loop.md by
# test_review_loop_reference_file_has_the_distinctive_prose below, so a
# phrase that drifts out of review-loop.md fails loudly here too).
DISTINCTIVE_REVIEW_LOOP_PROSE = [
    "/test-design",
    "[r/w/q]",
    "at most 2 rounds",
]

# The paired pointer sentence (Step 1.4's marker-plus-sentence convention) is
# always short — bound the strip so a future duplicate pasted with no blank
# line separator can't be silently swallowed past this many lines.
_MAX_PAIRED_SENTENCE_LINES = 4


def _strip_marker_and_paired_sentence(text: str, marker: str) -> str:
    """Remove the include-marker line and its immediately-following
    human-readable pointer sentence (the contiguous non-blank line run right
    after the marker — Step 1.4's marker-plus-sentence convention), leaving
    everything else untouched. Bounded to `_MAX_PAIRED_SENTENCE_LINES`: a
    pointer sentence run longer than that fails loudly instead of silently
    swallowing whatever follows (e.g. a duplicate pasted with no blank-line
    separator). A file may include the same marker at most once in this
    skill's convention, but this strips every occurrence defensively."""
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        if lines[i].strip() == marker:
            i += 1
            consumed = 0
            while i < len(lines) and lines[i].strip() != "":
                i += 1
                consumed += 1
                assert consumed <= _MAX_PAIRED_SENTENCE_LINES, (
                    f"paired pointer sentence after {marker!r} ran past "
                    f"{_MAX_PAIRED_SENTENCE_LINES} lines with no blank-line "
                    f"separator — this could be silently swallowing "
                    f"duplicated content instead of just the pointer sentence"
                )
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


def test_exactly_one_review_loop_reference_file_exists():
    matches = sorted(SKILL_DIR.glob("**/review-loop.md"))
    assert len(matches) == 1, f"expected exactly one review-loop.md, found {matches}"


@pytest.mark.parametrize("including_file", REVIEW_LOOP_INCLUDING_FILES, ids=lambda p: p.name)
def test_review_loop_including_file_names_it_via_include_marker(including_file):
    raw = including_file.read_text(encoding="utf-8")
    match = INCLUDE_RE.search(raw)
    assert match, f"{including_file.name} has no <!-- include: references/*.md --> marker"
    assert match.group(1) == "references/review-loop.md"


@pytest.mark.parametrize("including_file", REVIEW_LOOP_INCLUDING_FILES, ids=lambda p: p.name)
def test_review_loop_including_file_does_not_duplicate_content_outside_the_include(
    including_file,
):
    raw = including_file.read_text(encoding="utf-8")
    assert REVIEW_LOOP_INCLUDE_MARKER in raw  # positive clause, re-asserted for clarity

    stripped = _strip_marker_and_paired_sentence(raw, REVIEW_LOOP_INCLUDE_MARKER)

    for field in EVIDENCE_SCHEMA_FIELDS:
        assert field not in stripped, (
            f"evidence-schema field {field!r} appears in {including_file.name} "
            f"outside the review-loop.md include — it must live only in the "
            f"shared reference file"
        )
    for phrase in DISTINCTIVE_REVIEW_LOOP_PROSE:
        assert phrase not in stripped, (
            f"distinctive review-loop prose {phrase!r} appears in "
            f"{including_file.name} outside the review-loop.md include — it "
            f"must live only in the shared reference file"
        )


def test_review_loop_reference_file_opens_with_plain_prose_not_a_heading():
    """references/review-loop.md is included from inside another already-
    spliced-in reference file (phase-5-improve.md, and — since Step 1.10 —
    phase-7-refactor.md too), not from SKILL.md's own top level — the
    resolver's `_reject_h3_heading_at_depth` guard raises
    NestedHeadingLevelError if it opens with a `### ` heading. Pin the
    stronger, precedent-matching property directly: it opens with plain
    prose, not a heading at all (matching phase-0 through phase-4's
    reference files)."""
    review_loop = next(SKILL_DIR.glob("**/review-loop.md"))
    first_line = next(
        line for line in review_loop.read_text(encoding="utf-8").splitlines() if line.strip()
    )
    assert not first_line.startswith("#"), (
        f"references/review-loop.md must open with plain prose, not a "
        f"heading; got: {first_line!r}"
    )


def test_review_loop_reference_file_has_the_distinctive_prose():
    """Companion to the negative clause above: every phrase in
    DISTINCTIVE_REVIEW_LOOP_PROSE must actually exist in review-loop.md,
    or the negative clause's assertion of its absence elsewhere would be
    vacuous (asserting a phantom phrase is absent proves nothing)."""
    review_loop = next(SKILL_DIR.glob("**/review-loop.md"))
    text = review_loop.read_text(encoding="utf-8")
    for phrase in DISTINCTIVE_REVIEW_LOOP_PROSE:
        assert phrase in text, f"review-loop.md is missing distinctive prose {phrase!r}"


def test_review_loop_reference_file_contains_the_evidence_schema_fields():
    review_loop = next(SKILL_DIR.glob("**/review-loop.md"))
    text = review_loop.read_text(encoding="utf-8")
    for field in EVIDENCE_SCHEMA_FIELDS:
        assert field in text, f"review-loop.md is missing evidence-schema field {field!r}"
