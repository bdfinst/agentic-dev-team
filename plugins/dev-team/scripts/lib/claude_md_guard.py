"""Snapshot/diff/restore guards for tools that touch a project's `CLAUDE.md`.

Two distinct guards live here, for two distinct contracts:

**`run_install_with_guard`** — for `graphify install --project` (#846), which
rewrites the target repo's `CLAUDE.md` to add a `## graphify` section. Its
updater matches the literal `## graphify` header text and replaces everything
between it and the next `##` heading — a known bug can over-delete, removing
pre-existing unrelated content along with the stale graphify section.

1. Snapshot `CLAUDE.md` before running the installer.
2. Diff the snapshot against the post-install file.
3. If any pre-existing line was lost, restore the snapshot and append the
   canonical `## graphify` section text at EOF instead of trusting the
   installer's in-place edit.
4. If nothing was lost, leave the installer's output as-is.

**`run_install_reverting_unexpected_writes`** — for `repowise init` (#1670
item 3), which is documented (`project-init/SKILL.md`'s Step 4c prompt) as a
purely keyless, nothing-committed local index under `.repowise/`, but is
known to also append a `## Codebase Intelligence for <project> (Repowise)`
section straight into the tracked `.claude/CLAUDE.md` — content whose
project-name header text isn't fixed across repos the way graphify's is, so
there's no stable section marker to scope a corruption check to. Unlike the
`run_install_with_guard` contract, this one does not tolerate the write at
all: `CLAUDE.md` is expected to be **completely untouched**, so ANY diff —
added or removed lines, even a write followed by the installer itself
raising — is reverted in full. The reverted-or-not outcome and any added
lines are returned separately, so a deletion-only write is never mistaken
for a no-op.

Stdlib-only, per ADR 0014/0015 (Python for cross-OS scripts).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from pathlib import Path

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


def _lines_only_in(candidate_lines: list[str], baseline_counts: Counter) -> list[str]:
    """Multiset-diff kernel shared by `find_missing_lines`/`find_added_lines`:
    lines in `candidate_lines` that occur more often there than in
    `baseline_counts`. Order-preserving relative to `candidate_lines`. A line
    appearing twice in the candidate but only once in the baseline is
    reported once.
    """
    diff: list[str] = []
    seen = Counter()
    for line in candidate_lines:
        seen[line] += 1
        if seen[line] > baseline_counts[line]:
            diff.append(line)
    return diff


def find_missing_lines(old_text: str, new_text: str) -> list[str]:
    """Return lines present in `old_text` (outside its `## graphify` section)
    but missing (by multiset) from `new_text`.

    Order-preserving relative to `old_text`. A line that appears twice in
    `old_text` but only once in `new_text` is reported as missing once.
    """
    return _lines_only_in(_protected_lines(old_text), Counter(new_text.splitlines()))


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


def find_added_lines(old_text: str, new_text: str) -> list[str]:
    """Return lines present in `new_text` but missing (by multiset) from
    `old_text`. Order-preserving relative to `new_text`.

    Unlike `find_missing_lines`, this does NOT exclude any section — the
    Repowise contract this serves tolerates no section at all (see the module
    docstring), so excluding a `## graphify` body here would under-report a
    genuine addition landing inside one. Not a strict mirror of
    `find_missing_lines` for that reason; both share their multiset-diff
    logic via `_lines_only_in`.
    """
    return _lines_only_in(new_text.splitlines(), Counter(old_text.splitlines()))


def _read_or_none(path: Path) -> str | None:
    """Read `path`'s text, or `None` if it does not exist.

    A single call rather than a separate `exists()` + `read_text()` pair, so
    there is no window between the two where the file could be removed out
    from under this guard.
    """
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def run_install_reverting_unexpected_writes(
    claude_md_path: Path,
    installer: Callable[[], None],
) -> tuple[bool, list[str]]:
    """Run `installer()` against `claude_md_path`, reverting ANY write it made.

    Unlike `run_install_with_guard`, which expects and tolerates changes
    scoped to one known section, this treats `claude_md_path` as a file the
    installer must leave completely untouched. If `installer()` changed it at
    all (added or removed lines, or created/deleted the file), the pre-run
    state is restored — the file is rewritten to its snapshot, or deleted if
    it did not exist beforehand.

    Returns `(reverted, added)`: `reverted` is True iff anything changed and
    was undone. `added` lists any lines the installer had added — it is empty
    both when nothing changed AND when the installer only removed lines, so
    callers MUST branch on `reverted`, never on `bool(added)`, to decide
    whether anything happened (a deletion-only write still needs reporting).

    The revert runs even if `installer()` itself raises partway through a
    write — the compare-and-restore happens in a `finally` block, and the
    original exception still propagates once it completes.
    """
    snapshot = _read_or_none(claude_md_path)
    reverted = False
    added: list[str] = []

    try:
        installer()
    finally:
        post_install = _read_or_none(claude_md_path)
        if post_install != snapshot:
            reverted = True
            added = find_added_lines(snapshot or "", post_install or "")
            if snapshot is not None:
                claude_md_path.write_text(snapshot, encoding="utf-8")
            elif post_install is not None:
                claude_md_path.unlink()

    return reverted, added
