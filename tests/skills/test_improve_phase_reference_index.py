"""Content-guard for the `## Phase Reference Files` index added to
/test-improve's entry file (plan: test-improve-context-loading-strategy,
Slice 1, Step 1.3).

Step 1.4 onward have progressively moved phases' content out of SKILL.md
into their own `references/phase-<n>-*.md` files, spliced back in via
`<!-- include: ... -->` markers — check whether a phase's own body carries
an include marker (not the index table, which always lists all ten phases
regardless of split status — see
`test_every_phase_0_through_9_has_exactly_one_table_row` below) to tell
which phases have been split as of any given commit, since that count keeps
growing and this docstring would otherwise need updating every step. This
test checks the index table and its accompanying
instructions exist and are worded correctly, and additionally cross-checks
that every phase whose body already carries an include marker names the
exact same path in both the marker and the index table's path cell, and
that the target file exists on disk. Phases not yet split (no include
marker in their body) are only covered by the row-presence check below —
this test cannot verify a path for content that hasn't moved yet.
"""

from __future__ import annotations

import re

from skill_include_resolver import INCLUDE_RE, SKILL, SKILL_DIR


def _text() -> str:
    return SKILL.read_text()


def _normalized_text() -> str:
    """Collapse markdown hard line-wraps to single spaces so a phrase that
    wraps across source lines can still be matched as one substring."""
    return re.sub(r"\s+", " ", _text())


def test_phase_reference_files_heading_present():
    assert "## Phase Reference Files" in _text()


def test_on_demand_read_instruction_present():
    text = _normalized_text()
    assert "read only that phase's reference file" in text
    assert "already completed in this run or a prior resumed session" in text


def test_shared_reference_carve_out_present():
    text = _normalized_text()
    assert "not phase-specific" in text
    assert "references/review-loop.md" in text
    assert "regardless of whether another phase also uses them" in text


def test_instruction_is_stated_as_prose_not_hook_enforced():
    text = _normalized_text()
    assert "prose, not a hook-enforced gate" in text


def _phase_reference_files_table_body() -> str:
    section_match = re.search(
        r"^## Phase Reference Files\n(.*?)(?=\n### Phase 0)",
        _text(),
        re.MULTILINE | re.DOTALL,
    )
    assert section_match, "Could not locate the Phase Reference Files section body"
    return section_match.group(1)


def test_every_phase_0_through_9_has_exactly_one_table_row():
    table_body = _phase_reference_files_table_body()

    row_re = re.compile(r"^\|\s*(\d+)\s*\|", re.MULTILINE)
    rows = row_re.findall(table_body)

    assert sorted(rows, key=int) == [str(n) for n in range(10)]
    assert len(rows) == len(set(rows))


def _index_table_paths() -> dict[str, str]:
    """Map phase number -> the index table's `references/...` path cell for
    that phase."""
    row_re = re.compile(r"^\|\s*(\d+)\s*\|[^|]*\|\s*`([^`]+)`\s*\|", re.MULTILINE)
    return dict(row_re.findall(_phase_reference_files_table_body()))


def _phase_body_include_markers() -> dict[str, str]:
    """Map phase number -> the `<!-- include: ... -->` marker's path, for
    every `### Phase <n>` section whose body already carries one."""
    text = _text()
    markers: dict[str, str] = {}
    for match in re.finditer(r"^### Phase (\d+)\b.*$", text, re.MULTILINE):
        phase_num = match.group(1)
        section_start = match.end()
        boundary = re.search(r"^### ", text[section_start:], re.MULTILINE)
        section_end = section_start + boundary.start() if boundary else len(text)
        phase_body = text[section_start:section_end]
        include_match = INCLUDE_RE.search(phase_body)
        if include_match:
            markers[phase_num] = include_match.group(1)
    return markers


def test_index_table_paths_match_body_include_markers_where_present():
    index_paths = _index_table_paths()
    body_markers = _phase_body_include_markers()

    assert body_markers, "expected at least one phase to already carry an include marker"
    for phase_num, marker_path in body_markers.items():
        assert phase_num in index_paths, (
            f"Phase {phase_num} has a body include marker but no index table row"
        )
        assert index_paths[phase_num] == marker_path, (
            f"Phase {phase_num}: index table names {index_paths[phase_num]!r} "
            f"but the body's include marker names {marker_path!r}"
        )
        assert (SKILL_DIR / marker_path).is_file(), (
            f"Phase {phase_num}'s reference file {marker_path!r} does not exist on disk"
        )
