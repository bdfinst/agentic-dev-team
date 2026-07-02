"""Shared helpers for the tests/skills/ pytest port of tests/skills/*.bats
(issue #674, epic #668).

These are structural sensors over shipped SKILL.md prose — pure text greps,
no state-mutating git/filesystem operations — so most files here need
nothing beyond a path constant and the helpers below. Files that DO shell
out to a script use pytest's built-in `tmp_path` fixture for hermetic
tempdirs (replacing `mktemp -d` + `rm -rf`) instead of anything from
tests/lib/hermetic.bash.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "dev-team"


def _posix_classes(pattern: str) -> str:
    """POSIX bracket classes (`[[:space:]]`, ...) aren't valid inside
    Python's `re` — the bats originals use them freely (they run through
    GNU/BSD grep -E), so translate the handful that appear in this test
    tree to their `re` equivalents."""
    return pattern.replace("[[:space:]]", r"\s").replace("[[:alnum:]]", r"[A-Za-z0-9]")


def grep(pattern: str, text: str, ignore_case: bool = False) -> bool:
    """Mirror `grep -Eq[i] <pattern>` — extended-regex search, boolean.

    `grep` matches per-line, so `^`/`$` anchor to line boundaries even when
    `text` spans many lines (a multi-line string built by `section()` or
    read straight from a file) — hence re.MULTILINE, always on.
    """
    flags = re.MULTILINE | (re.IGNORECASE if ignore_case else 0)
    return re.search(_posix_classes(pattern), text, flags) is not None


def grep_multiline(pattern: str, text: str, ignore_case: bool = False) -> bool:
    """Mirror `grep -Eqz[i]` — null-record mode lets the pattern span
    newlines within the haystack (grep -z joins the whole input into one
    NUL-terminated record before applying the regex)."""
    flags = re.IGNORECASE | re.DOTALL if ignore_case else re.DOTALL
    return re.search(_posix_classes(pattern), text, flags) is not None


def frontmatter(text: str) -> str:
    """Mirror `awk 'NR>1 && /^---/{exit} {print}'` — the YAML frontmatter
    block between the opening `---` (line 1, always skipped by NR>1) and
    the closing `---`."""
    lines = text.splitlines()
    out: list[str] = []
    for i, line in enumerate(lines):
        if i > 0 and line.startswith("---"):
            break
        out.append(line)
    return "\n".join(out)


def section(text: str, start_pattern: str, exclude_pattern: str | None = None) -> str:
    """Mirror the repeated awk idiom:

        /<start_pattern>/ {inphase=1; print; next}
        inphase && /^### / {exit}
        inphase {print}

    Extracts from the first line matching `start_pattern` up to (but not
    including) the next `### `-prefixed header line. `exclude_pattern`,
    when given, mirrors `&& !/<exclude_pattern>/` guarding the start match
    (used by the Phase 2 vs Phase 2b disambiguation).
    """
    lines = text.splitlines()
    start_re = re.compile(start_pattern)
    exclude_re = re.compile(exclude_pattern) if exclude_pattern else None
    out: list[str] = []
    inphase = False
    for line in lines:
        if not inphase and start_re.search(line):
            if exclude_re is not None and exclude_re.search(line):
                continue
            inphase = True
            out.append(line)
            continue
        if inphase and re.match(r"^### ", line):
            break
        if inphase:
            out.append(line)
    return "\n".join(out)
