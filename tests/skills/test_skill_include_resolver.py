"""Tests for the recursive include-marker resolver added in Step 1.1 of
plans/test-improve-context-loading-strategy.md (Slice 1).

Covers the five cases the plan enumerates for `resolve_test_improve_text()` /
its underlying `_resolve()`: (a) no-op on text with no include markers
(originally asserted directly against the real, not-yet-split
test-improve/SKILL.md; Step 1.4 began moving real content into
references/, so the no-op property is now proven against a synthetic
fixture instead of the evolving real file); (b) a single-level include splice recovered
correctly by `section()`; (c) a valid two-level nested include (the shared
inner file opens with `#### `, not `### `); (d) the authoring-constraint
violation — the shared inner file wrongly opens with `### ` — raising
`NestedHeadingLevelError`; (e) a dangling include marker raising
`FileNotFoundError`.
"""

from __future__ import annotations

import pytest
from skill_doc_helpers import section
from skill_include_resolver import _MAX_INCLUDE_DEPTH, NestedHeadingLevelError
from skill_include_resolver import _resolve_includes as _resolve

# skill_include_resolver.resolve_test_improve_text is not imported here: this
# file only exercises `_resolve()` directly against synthetic fixtures, so
# that entry point is never needed.


def test_no_op_when_no_include_markers_present(tmp_path):
    """(a) Text with no `<!-- include: ... -->` markers resolves as a
    byte-for-byte no-op. Originally asserted directly against the real,
    not-yet-split test-improve/SKILL.md; Step 1.4 (plans/
    test-improve-context-loading-strategy.md) began moving real phase
    content out to references/, so SKILL.md itself now legitimately
    contains include markers and can no longer serve as the "no markers"
    fixture. The no-op property this case exists to prove is unchanged —
    it is now proven against a synthetic fixture instead."""
    skill_text = "### Phase X\nNo include markers here.\n"
    assert _resolve(skill_text, depth=0, base=tmp_path) == skill_text


def test_single_level_include_recovered_by_section(tmp_path):
    """(b) A fake SKILL.md with one phase replaced by an include-marker
    stub, and a fake references/phase-x.md holding that phase's real
    content — `section()` must recover the real content, not the marker
    line."""
    skill_text = (
        "### Phase X\n"
        "<!-- include: references/phase-x.md -->\n"
        "### Phase Y\n"
        "Phase Y content.\n"
    )
    references = tmp_path / "references"
    references.mkdir()
    (references / "phase-x.md").write_text("Placeholder body for Phase X.\n")

    resolved = _resolve(skill_text, depth=0, base=tmp_path)

    phase_x = section(resolved, r"^### Phase X")
    assert phase_x == "### Phase X\nPlaceholder body for Phase X.\n"


def test_nested_include_recovered_when_shared_file_uses_h4(tmp_path):
    """(c) The nested case: references/phase-x.md itself includes
    references/shared.md, which opens with `#### ` (never `### `) — the
    fully-resolved text must recover both the phase file's own text and
    the shared file's spliced-in body, unbroken by a false `### ` boundary
    match."""
    skill_text = (
        "### Phase X\n"
        "<!-- include: references/phase-x.md -->\n"
        "### Phase Y\n"
        "Phase Y content.\n"
    )
    references = tmp_path / "references"
    references.mkdir()
    (references / "phase-x.md").write_text(
        "Phase X own text before.\n"
        "<!-- include: references/shared.md -->\n"
        "Phase X own text after.\n"
    )
    (references / "shared.md").write_text(
        "#### Shared Heading\nShared body text.\n"
    )

    resolved = _resolve(skill_text, depth=0, base=tmp_path)

    phase_x = section(resolved, r"^### Phase X")
    assert phase_x == (
        "### Phase X\n"
        "Phase X own text before.\n"
        "#### Shared Heading\n"
        "Shared body text.\n"
        "\n"
        "Phase X own text after.\n"
    )


def test_nested_include_with_h3_shared_file_raises(tmp_path):
    """(d) Same nested fixture as (c), but references/shared.md wrongly
    opens with `### ` — must raise NestedHeadingLevelError naming
    references/shared.md, exercising the depth-check branch directly."""
    skill_text = (
        "### Phase X\n"
        "<!-- include: references/phase-x.md -->\n"
        "### Phase Y\n"
        "Phase Y content.\n"
    )
    references = tmp_path / "references"
    references.mkdir()
    (references / "phase-x.md").write_text(
        "Phase X own text before.\n"
        "<!-- include: references/shared.md -->\n"
        "Phase X own text after.\n"
    )
    (references / "shared.md").write_text(
        "### Shared Heading\nShared body text.\n"
    )

    with pytest.raises(NestedHeadingLevelError, match="references/shared.md"):
        _resolve(skill_text, depth=0, base=tmp_path)


def test_nested_include_with_h3_heading_mid_body_raises(tmp_path):
    """(d2) Whole-file variant of (d): references/shared.md's *first* line
    is valid (`#### ` heading), but a `### ` heading appears further down in
    its body — must still raise NestedHeadingLevelError naming
    references/shared.md, proving the guard scans the whole file rather
    than only the first non-blank line."""
    skill_text = (
        "### Phase X\n"
        "<!-- include: references/phase-x.md -->\n"
        "### Phase Y\n"
        "Phase Y content.\n"
    )
    references = tmp_path / "references"
    references.mkdir()
    (references / "phase-x.md").write_text(
        "Phase X own text before.\n"
        "<!-- include: references/shared.md -->\n"
        "Phase X own text after.\n"
    )
    (references / "shared.md").write_text(
        "#### Shared Heading\n"
        "Shared body text.\n"
        "### Mid-body offender\n"
        "More shared body text.\n"
    )

    with pytest.raises(NestedHeadingLevelError, match="references/shared.md"):
        _resolve(skill_text, depth=0, base=tmp_path)


def test_dangling_include_marker_raises_file_not_found(tmp_path):
    """(e) An include marker naming a references/*.md path that does not
    exist on disk must raise FileNotFoundError naming the missing path and
    the marker line — never a silent pass-through of the raw marker line."""
    skill_text = (
        "### Phase X\n"
        "<!-- include: references/does-not-exist.md -->\n"
        "### Phase Y\n"
        "Phase Y content.\n"
    )

    with pytest.raises(FileNotFoundError, match="references/does-not-exist.md"):
        _resolve(skill_text, depth=0, base=tmp_path)


def test_include_cycle_raises_recursion_error(tmp_path):
    """(f) Two reference files that include each other must raise
    RecursionError once the include chain exceeds `_MAX_INCLUDE_DEPTH` —
    never loop indefinitely or silently truncate."""
    skill_text = "### Phase X\n<!-- include: references/a.md -->\n"
    references = tmp_path / "references"
    references.mkdir()
    (references / "a.md").write_text("<!-- include: references/b.md -->\n")
    (references / "b.md").write_text("<!-- include: references/a.md -->\n")

    with pytest.raises(RecursionError, match="include recursion exceeded depth"):
        _resolve(skill_text, depth=0, base=tmp_path)


def test_legitimate_chain_at_exactly_max_include_depth_resolves_without_raising(
    tmp_path,
):
    """(g) Boundary-success counterpart to (f): a non-cyclic chain of
    exactly `_MAX_INCLUDE_DEPTH` (5) nested includes — level1.md includes
    level2.md, ... level4.md includes level5.md, and level5.md is a plain
    leaf with no further include marker — must resolve successfully. The
    deepest `_resolve_includes()` call in this chain runs at `depth == 5`,
    exactly `_MAX_INCLUDE_DEPTH`; only `depth > _MAX_INCLUDE_DEPTH` (i.e.
    depth 6, reached one level deeper) may raise. Proves the boundary
    comparison isn't off-by-one on the passing side, mirroring (f)'s proof
    on the failing side."""
    skill_text = "### Phase X\n<!-- include: references/level1.md -->\n"
    references = tmp_path / "references"
    references.mkdir()
    for level in range(1, _MAX_INCLUDE_DEPTH):
        (references / f"level{level}.md").write_text(
            f"Level {level} text.\n"
            f"<!-- include: references/level{level + 1}.md -->\n"
        )
    (references / f"level{_MAX_INCLUDE_DEPTH}.md").write_text(
        f"Level {_MAX_INCLUDE_DEPTH} leaf text.\n"
    )

    resolved = _resolve(skill_text, depth=0, base=tmp_path)

    phase_x = section(resolved, r"^### Phase X")
    expected_lines = [f"Level {level} text." for level in range(1, _MAX_INCLUDE_DEPTH)]
    expected_lines.append(f"Level {_MAX_INCLUDE_DEPTH} leaf text.")
    assert phase_x == (
        "### Phase X\n"
        + "".join(f"{line}\n" for line in expected_lines)
        + "\n" * (_MAX_INCLUDE_DEPTH - 1)
    )
