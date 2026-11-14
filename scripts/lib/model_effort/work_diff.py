"""What a write-capable trial changed: its working copy against the frozen fixture.

The diff is computed by the harness, not taken from the agent's answer or from
the trial's own git repo (which the agent can rewrite), so a rubric judge can
check what the agent claims it changed and what it was told to leave alone.
"""

from __future__ import annotations

import difflib
from pathlib import Path

# The diff is capped so a large rewrite cannot crowd out the rest of the judge's prompt.
DIFF_MAX_CHARS = 30_000
DIFF_TRUNCATED_NOTE = "[diff truncated]"
NO_CHANGES_TEXT = "(no files changed)"
# The trial's own git repo, made by the harness; its contents are not the agent's work.
_SKIPPED_PARTS = frozenset({".git"})


def _entries(root: Path) -> dict[str, Path]:
    """Every file and symlink under `root` (or `root` itself, a file), by relative POSIX path."""
    if root.is_file() and not root.is_symlink():
        return {root.name: root}
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if (path.is_symlink() or path.is_file())
        and not _SKIPPED_PARTS & set(path.relative_to(root).parts)
    }


def _describe(path: Path) -> list[str] | str:
    """A file's lines, or a one-line description of a symlink or binary file."""
    if path.is_symlink():
        return f"symlink to {path.readlink()}"
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return f"binary file, {path.stat().st_size} bytes"
    if "\x00" in text:
        return f"binary file, {path.stat().st_size} bytes"
    return text.splitlines(keepends=True)


def _label(described: list[str] | str, present: bool) -> str:
    if isinstance(described, str):
        return described
    return "a text file" if present else "absent"


def working_copy_diff(
    pristine: Path, work: Path, max_chars: int = DIFF_MAX_CHARS
) -> str:
    """A unified diff from `pristine` to `work`, `.git` skipped, capped at `max_chars`.

    Symlinks are described, never followed; a file that is not UTF-8 text is
    named with its size.
    """
    before, after = _entries(pristine), _entries(work)
    sections = []
    for name in sorted(before.keys() | after.keys()):
        old = _describe(before[name]) if name in before else []
        new = _describe(after[name]) if name in after else []
        if old == new:
            continue
        if isinstance(old, str) or isinstance(new, str):
            was, now = _label(old, name in before), _label(new, name in after)
            sections.append(f"--- a/{name}\n+++ b/{name}\n! was {was}; now {now}\n")
            continue
        sections.append(
            "".join(
                difflib.unified_diff(
                    old,
                    new,
                    fromfile=f"a/{name}" if name in before else "/dev/null",
                    tofile=f"b/{name}" if name in after else "/dev/null",
                )
            )
        )
    diff = "\n".join(section.rstrip("\n") for section in sections)
    if not diff:
        return NO_CHANGES_TEXT
    if len(diff) > max_chars:
        diff = diff[:max_chars] + f"\n\n{DIFF_TRUNCATED_NOTE}"
    return diff
