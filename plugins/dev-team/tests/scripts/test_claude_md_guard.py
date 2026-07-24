"""Unit tests for scripts/lib/claude_md_guard.py (#846).

Validates the snapshot -> diff -> restore-or-append guard project-init's
Step 4c wraps around `graphify install --project`. Does NOT exercise the
real graphify binary (not installed in this sandbox) — it stubs a
"corrupting installer" that reproduces the documented over-deletion bug
(matches literal `## graphify` and deletes through the next `##` heading,
including content that should have survived) and asserts the guard never
loses pre-existing content.
"""

from __future__ import annotations

import sys
from pathlib import Path

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "scripts" / "lib"))

import claude_md_guard

FIXTURE_CLAUDE_MD = """\
# Root

## Section A
content a

## graphify
stale graphify section from a previous run

## Section B
content b
"""

CANONICAL_GRAPHIFY_SECTION = """\
## graphify
This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists.
"""


def _corrupting_installer(path: Path) -> None:
    """Reproduce the documented over-deletion bug.

    Finds the literal `## graphify` header and deletes everything from that
    line through the *end* of the next `##` heading's body (over-deleting —
    the real bug deletes more than just the stale graphify section, taking
    unrelated content with it).
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == "## graphify")

    # Find the next "##" heading after start.
    next_heading = None
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("## "):
            next_heading = i
            break

    if next_heading is None:
        end = len(lines)
    else:
        # Over-delete: consume the next heading's entire body too, not just
        # the stale graphify section — this is the bug being reproduced.
        end = len(lines)

    corrupted = lines[:start] + lines[end:]
    path.write_text("\n".join(corrupted) + "\n", encoding="utf-8")


def _clean_installer(path: Path, new_section: str) -> None:
    """A well-behaved installer that only replaces the graphify section."""
    lines = path.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == "## graphify")
    end = None
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("## "):
            end = i
            break
    if end is None:
        end = len(lines)
    replaced = lines[:start] + new_section.splitlines() + lines[end:]
    path.write_text("\n".join(replaced) + "\n", encoding="utf-8")


def test_find_missing_lines_detects_lost_content():
    old = "a\nb\nc\n"
    new = "a\nc\n"
    assert claude_md_guard.find_missing_lines(old, new) == ["b"]


def test_find_missing_lines_none_lost():
    old = "a\nb\nc\n"
    new = "a\nb\nc\nd\n"
    assert claude_md_guard.find_missing_lines(old, new) == []


def test_guard_repairs_corrupting_installer(tmp_path: Path):
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text(FIXTURE_CLAUDE_MD, encoding="utf-8")
    original_lines = FIXTURE_CLAUDE_MD.splitlines()

    repaired = claude_md_guard.run_install_with_guard(
        claude_md,
        installer=lambda: _corrupting_installer(claude_md),
        canonical_section=CANONICAL_GRAPHIFY_SECTION,
    )

    assert repaired is True

    final_text = claude_md.read_text(encoding="utf-8")
    final_lines = final_text.splitlines()

    for line in original_lines:
        assert line in final_lines, f"lost pre-existing line: {line!r}"

    # The canonical section was appended, not silently dropped.
    assert "## graphify" in final_text
    assert "graphify query" in final_text


def test_guard_leaves_clean_install_untouched(tmp_path: Path):
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text(FIXTURE_CLAUDE_MD, encoding="utf-8")
    original_lines = FIXTURE_CLAUDE_MD.splitlines()

    repaired = claude_md_guard.run_install_with_guard(
        claude_md,
        installer=lambda: _clean_installer(claude_md, CANONICAL_GRAPHIFY_SECTION),
        canonical_section=CANONICAL_GRAPHIFY_SECTION,
    )

    assert repaired is False

    final_lines = claude_md.read_text(encoding="utf-8").splitlines()
    for line in original_lines:
        if line.strip() == "stale graphify section from a previous run":
            continue  # this line is expected to be replaced by a clean install
        assert line in final_lines, f"lost pre-existing line: {line!r}"
