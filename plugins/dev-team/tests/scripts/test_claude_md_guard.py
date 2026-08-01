"""Unit tests for scripts/lib/claude_md_guard.py (#846, #1670 item 3).

Validates two distinct guards:

- The snapshot -> diff -> restore-or-append guard project-init's Step 4c
  wraps around `graphify install --project`. Does NOT exercise the real
  graphify binary (not installed in this sandbox) — it stubs a "corrupting
  installer" that reproduces the documented over-deletion bug (matches
  literal `## graphify` and deletes through the next `##` heading, including
  content that should have survived) and asserts the guard never loses
  pre-existing content.
- The snapshot -> diff -> full-revert guard for `repowise init`, which is
  documented as writing nothing to the repo but is known to append a section
  to `.claude/CLAUDE.md` anyway (#1670 item 3). Stubs a "writing installer"
  that reproduces that append and asserts the guard reverts it completely,
  reporting exactly what was reverted.
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


REPOWISE_SECTION = """\
## Codebase Intelligence for agentic-dev-team (Repowise)
Indexed at commit deadbeef on 2026-01-01. Health score: 87/100.
"""


def _repowise_writing_installer(path: Path) -> None:
    """Reproduce Repowise's real behavior: append an unannounced section to
    the tracked CLAUDE.md, on top of whatever else it does (index build,
    .mcp.json write) that this guard doesn't need to know about."""
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if not existing.endswith("\n"):
        existing += "\n"
    path.write_text(existing + "\n" + REPOWISE_SECTION, encoding="utf-8")


def _no_op_installer(path: Path) -> None:
    """A well-behaved installer that genuinely writes nothing to CLAUDE.md."""


def _removing_installer(path: Path) -> None:
    """An installer that only DELETES existing content, adding nothing — the
    diff shape `added` alone cannot report (#1670 item 3 review finding: a
    deletion-only revert must not look like a no-op to the caller)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    trimmed = [line for line in lines if line.strip() != "content a"]
    path.write_text("\n".join(trimmed) + "\n", encoding="utf-8")


def _raising_installer(path: Path) -> None:
    """An installer that writes its section and then fails partway through —
    e.g. a real index-build error after the CLAUDE.md append already
    happened. The guard must still revert the write before the exception
    propagates."""
    _repowise_writing_installer(path)
    raise RuntimeError("simulated repowise index-build failure")


def test_find_added_lines_detects_new_content():
    old = "a\nb\n"
    new = "a\nb\nc\n"
    assert claude_md_guard.find_added_lines(old, new) == ["c"]


def test_find_added_lines_none_added():
    old = "a\nb\nc\n"
    new = "a\nb\n"
    assert claude_md_guard.find_added_lines(old, new) == []


def test_find_added_lines_duplicate_line_counted_once():
    old = "a\n"
    new = "a\na\na\n"
    assert claude_md_guard.find_added_lines(old, new) == ["a", "a"]


def test_find_missing_lines_duplicate_line_counted_once():
    old = "a\na\na\n"
    new = "a\n"
    assert claude_md_guard.find_missing_lines(old, new) == ["a", "a"]


def test_reverting_guard_undoes_an_unexpected_write(tmp_path: Path):
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text(FIXTURE_CLAUDE_MD, encoding="utf-8")

    reverted, added = claude_md_guard.run_install_reverting_unexpected_writes(
        claude_md,
        installer=lambda: _repowise_writing_installer(claude_md),
    )

    assert reverted is True
    # _repowise_writing_installer inserts one blank-line separator before the
    # section, same as run_install_with_guard's own canonical_section append.
    assert added == ["", *REPOWISE_SECTION.splitlines()]

    final_text = claude_md.read_text(encoding="utf-8")
    assert final_text == FIXTURE_CLAUDE_MD
    assert "Codebase Intelligence" not in final_text


def test_reverting_guard_leaves_a_true_no_op_untouched(tmp_path: Path):
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text(FIXTURE_CLAUDE_MD, encoding="utf-8")

    reverted, added = claude_md_guard.run_install_reverting_unexpected_writes(
        claude_md,
        installer=lambda: _no_op_installer(claude_md),
    )

    assert reverted is False
    assert added == []
    assert claude_md.read_text(encoding="utf-8") == FIXTURE_CLAUDE_MD


def test_reverting_guard_deletes_a_file_the_installer_created(tmp_path: Path):
    """CLAUDE.md may not exist at all before the first `repowise init` in a
    repo that has none yet — the guard must remove the file it created, not
    leave the unexpected write in place because "restore the snapshot" has
    nothing to restore to."""
    claude_md = tmp_path / "CLAUDE.md"
    assert not claude_md.exists()

    reverted, added = claude_md_guard.run_install_reverting_unexpected_writes(
        claude_md,
        installer=lambda: claude_md.write_text(REPOWISE_SECTION, encoding="utf-8"),
    )

    assert reverted is True
    assert added == REPOWISE_SECTION.splitlines()
    assert not claude_md.exists()


def test_reverting_guard_reports_a_deletion_only_write_as_reverted(tmp_path: Path):
    """A write that only REMOVES lines (no additions) must still report
    `reverted=True` — `added` alone is `[]` for both this case and a true
    no-op, so the caller cannot use `bool(added)` to tell them apart."""
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text(FIXTURE_CLAUDE_MD, encoding="utf-8")

    reverted, added = claude_md_guard.run_install_reverting_unexpected_writes(
        claude_md,
        installer=lambda: _removing_installer(claude_md),
    )

    assert reverted is True
    assert added == []
    assert claude_md.read_text(encoding="utf-8") == FIXTURE_CLAUDE_MD


def test_reverting_guard_restores_even_when_installer_raises(tmp_path: Path):
    """A real `repowise init` can append its section and then fail later in
    the same run (index-build error, network, tool crash) — the guard must
    still revert the write, and the original exception must still surface
    to the caller rather than being swallowed."""
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text(FIXTURE_CLAUDE_MD, encoding="utf-8")

    try:
        claude_md_guard.run_install_reverting_unexpected_writes(
            claude_md,
            installer=lambda: _raising_installer(claude_md),
        )
        raise AssertionError("expected the installer's RuntimeError to propagate")
    except RuntimeError as exc:
        assert "simulated repowise index-build failure" in str(exc)

    assert claude_md.read_text(encoding="utf-8") == FIXTURE_CLAUDE_MD
