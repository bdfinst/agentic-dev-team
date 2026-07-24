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


def phase_8_section(text: str) -> str:
    """Extract /test-improve's Phase 8 section from `text` (the skill's full
    body). Promoted here (test-smell-review, issue #968) after the same
    one-line `section(text, r"^### Phase 8")` wrapper was duplicated
    verbatim across three tests/skills/test_improve_*.py files."""
    return section(text, r"^### Phase 8")


def collapsed(text: str) -> str:
    """Collapse all whitespace runs (including newlines) to single spaces so
    a phrase hard-wrapped across markdown lines — even mid-word — still
    matches a literal substring/grep check that assumes single-line prose.
    Structure-review (issue #968) found this reimplemented inline in
    multiple test files; this is the one shared implementation."""
    return " ".join(text.split())


def grep_multiline(pattern: str, text: str, ignore_case: bool = False) -> bool:
    """Mirror `grep -Eqz[i]` — null-record mode lets the pattern span
    newlines within the haystack (grep -z joins the whole input into one
    NUL-terminated record before applying the regex)."""
    flags = re.IGNORECASE | re.DOTALL if ignore_case else re.DOTALL
    return re.search(_posix_classes(pattern), text, flags) is not None


def first_line_outside_code(text: str, pattern: str) -> int | None:
    """Mirror the repeated awk idiom:

        /^```/ { code = !code; next }
        !code && /<pattern>/ { print NR; exit }

    Returns the 1-based line number of the first match found outside a
    fenced code block, or None if no such line exists.
    """
    pattern_re = re.compile(_posix_classes(pattern))
    code = False
    for lineno, line in enumerate(text.splitlines(), start=1):
        if line.startswith("```"):
            code = not code
            continue
        if not code and pattern_re.search(line):
            return lineno
    return None


def section_outside_code(
    text: str,
    start_pattern: str,
    boundary_pattern: str = r"^## ",
    include_start_line: bool = False,
) -> str:
    """Mirror the repeated awk idiom:

        /^```/                 { code = !code; next }
        !code && /<start>/     { f=1; next }
        !code && /<boundary>/  { f=0 }
        f { print }

    Section extraction that ignores fenced-code-block content when
    matching header boundaries (used by the mutation-testing SKILL.md
    contracts, whose sections contain embedded ``` examples that must not
    be mistaken for a `## `-prefixed header)."""
    lines = text.splitlines()
    start_re = re.compile(_posix_classes(start_pattern))
    boundary_re = re.compile(_posix_classes(boundary_pattern))
    out: list[str] = []
    inphase = False
    code = False
    for line in lines:
        if line.startswith("```"):
            code = not code
            continue
        if code:
            if inphase:
                out.append(line)
            continue
        if not inphase and start_re.search(line):
            inphase = True
            if include_start_line:
                out.append(line)
            continue
        if inphase and boundary_re.match(line):
            inphase = False
            continue
        if inphase:
            out.append(line)
    return "\n".join(out)


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


def section(
    text: str,
    start_pattern: str,
    exclude_pattern: str | None = None,
    boundary_pattern: str = r"^### ",
    include_start_line: bool = True,
) -> str:
    """Mirror the repeated awk idiom:

        /<start_pattern>/ {inphase=1; print; next}
        inphase && /<boundary_pattern>/ {exit}
        inphase {print}

    Extracts from the first line matching `start_pattern` up to (but not
    including) the next line matching `boundary_pattern` (defaults to the
    `### `-prefixed header level used by the /test-improve phase files;
    pass `r"^## "` for the `## `-level sections used elsewhere, e.g.
    `## Constraints`). `exclude_pattern`, when given, mirrors
    `&& !/<exclude_pattern>/` guarding the start match (used by the
    Phase 2 vs Phase 3 disambiguation). `include_start_line=False`
    mirrors the `{f=1; next}` idiom (start header consumed, not printed).
    """
    lines = text.splitlines()
    start_re = re.compile(start_pattern)
    exclude_re = re.compile(exclude_pattern) if exclude_pattern else None
    boundary_re = re.compile(boundary_pattern)
    out: list[str] = []
    inphase = False
    for line in lines:
        if not inphase and start_re.search(line):
            if exclude_re is not None and exclude_re.search(line):
                continue
            inphase = True
            if include_start_line:
                out.append(line)
            continue
        if inphase and boundary_re.match(line):
            break
        if inphase:
            out.append(line)
    return "\n".join(out)
