"""Snapshot/diff/restore guard for `graphify install --project` (#846).

`graphify install --project` rewrites the target repo's `CLAUDE.md` to add a
`## graphify` section. Its updater matches the literal `## graphify` header
text and replaces everything between it and the next `##` heading — a known
bug can over-delete, removing pre-existing unrelated content along with the
stale graphify section.

This module implements the guard `project-init`'s Step 4c documents:

1. Snapshot `CLAUDE.md` before running the installer.
2. Diff the snapshot against the post-install file.
3. If any pre-existing line was lost, restore the snapshot and append the
   canonical `## graphify` section text at EOF instead of trusting the
   installer's in-place edit.
4. If nothing was lost, leave the installer's output as-is.

Stdlib-only, per ADR 0014/0015 (Python for cross-OS scripts).
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Callable


_GRAPHIFY_HEADER = "## graphify"


def _protected_lines(text: str) -> list[str]:
    """All lines of `text` except the existing `## graphify` section's body.

    The graphify section is expected to change on every install (that's the
    point of re-running the installer) so it is excluded from the
    corruption check — only lines *outside* that section must survive.
    """
    lines = text.splitlines()
    start = next(
        (i for i, line in enumerate(lines) if line.strip() == _GRAPHIFY_HEADER),
        None,
    )
    if start is None:
        return lines

    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("## "):
            end = i
            break

    return lines[:start] + lines[end:]


def find_missing_lines(old_text: str, new_text: str) -> list[str]:
    """Return lines present in `old_text` (outside its `## graphify` section)
    but missing (by multiset) from `new_text`.

    Order-preserving relative to `old_text`. A line that appears twice in
    `old_text` but only once in `new_text` is reported as missing once.
    """
    old_lines = _protected_lines(old_text)
    new_counts = Counter(new_text.splitlines())
    missing: list[str] = []
    seen = Counter()
    for line in old_lines:
        seen[line] += 1
        if seen[line] > new_counts[line]:
            missing.append(line)
    return missing


def run_install_with_guard(
    claude_md_path: Path,
    installer: Callable[[], None],
    canonical_section: str,
) -> bool:
    """Run `installer()` against `claude_md_path` under the corruption guard.

    Returns True if corruption was detected and repaired (snapshot restored
    + canonical section appended), False if the installer's output was left
    as-is because nothing pre-existing was lost.
    """
    snapshot = claude_md_path.read_text(encoding="utf-8")

    installer()

    post_install = claude_md_path.read_text(encoding="utf-8")
    missing = find_missing_lines(snapshot, post_install)

    if not missing:
        return False

    repaired = snapshot
    if not repaired.endswith("\n"):
        repaired += "\n"
    if not canonical_section.startswith("\n"):
        repaired += "\n"
    repaired += canonical_section
    claude_md_path.write_text(repaired, encoding="utf-8")
    return True
