"""What a write-capable trial changed: its working copy against the frozen fixture.

The diff is computed by the harness, not taken from the agent's answer or from
the trial's own git repo (which the agent can rewrite), so a rubric judge can
check what the agent claims it changed and what it was told to leave alone.
"""

from __future__ import annotations

import difflib
import hashlib
from pathlib import Path

# The diff is capped so a large rewrite cannot crowd out the rest of the judge's prompt.
DIFF_MAX_CHARS = 30_000
DIFF_TRUNCATED_NOTE = "[diff truncated]"
NO_CHANGES_TEXT = "(no files changed)"
# The trial's own git repo, made by the harness at the top of the copy; its
# contents are not the agent's work. A `.git` deeper down is the agent's.
_HARNESS_GIT_DIR = ".git"


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
        and path.relative_to(root).parts[0] != _HARNESS_GIT_DIR
    }


def _describe(path: Path) -> list[str] | str:
    """A file's lines, or a one-line description of a symlink or binary file.

    A binary file is named by its size and SHA-256, so a same-size change shows.
    """
    if path.is_symlink():
        return f"symlink to {path.readlink()}"
    try:
        data = path.read_bytes()
    except OSError as error:
        return f"unreadable file ({type(error).__name__})"
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return _binary(data)
    if "\x00" in text:
        return _binary(data)
    return text.splitlines(keepends=True)


def _binary(data: bytes) -> str:
    return f"binary file, {len(data)} bytes, sha256 {hashlib.sha256(data).hexdigest()}"


def _label(described: list[str] | str, present: bool) -> str:
    if not present:
        return "absent"
    if isinstance(described, str):
        return described
    return "a text file" if described else "an empty file"


def working_copy_diff(
    pristine: Path, work: Path, max_chars: int = DIFF_MAX_CHARS
) -> str:
    """A unified diff from `pristine` to `work`, `.git` skipped, capped at `max_chars`.

    Symlinks are described, never followed; a file that is not UTF-8 text is
    named with its size and SHA-256. An empty file created or deleted gets a
    labeled section, since a line diff of it is empty.
    """
    before, after = _entries(pristine), _entries(work)
    sections = []
    for name in sorted(before.keys() | after.keys()):
        was_present, is_present = name in before, name in after
        old = _describe(before[name]) if was_present else []
        new = _describe(after[name]) if is_present else []
        if old == new and was_present == is_present:
            continue
        # A unified diff of two empty line lists is empty, so an empty file
        # created or deleted gets a labeled section like a binary file does.
        if isinstance(old, str) or isinstance(new, str) or not (old or new):
            was, now = _label(old, was_present), _label(new, is_present)
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
