"""Include-marker resolver for /test-improve's SKILL.md, shared by the
tests/skills/test_improve_*.py content-guard suite (plus a couple of
adjacent files that cross-check test-improve's fully-resolved text).

Split out of skill_doc_helpers.py (structure-review): skill_doc_helpers is
generic shared infrastructure used by 116 test files across many skills,
and this module's `<!-- include: ... -->` splicing is test-improve-specific
machinery that was drifting that shared module toward one consumer's
concerns. Deliberately not `test_`-prefixed so pytest never tries to
collect this module itself as a set of tests.
"""

from __future__ import annotations

import re
from pathlib import Path

from skill_doc_helpers import PLUGIN_ROOT

SKILL_DIR = PLUGIN_ROOT / "skills" / "test-improve"
SKILL = SKILL_DIR / "SKILL.md"

INCLUDE_RE = re.compile(r"^<!-- include: (references/[^\s]+\.md) -->$", re.MULTILINE)
_MAX_INCLUDE_DEPTH = 5


class NestedHeadingLevelError(Exception):
    """Raised by `_resolve_includes()` when a `references/*.md` file spliced
    in at depth >= 1 (i.e. included from inside another already-spliced-in
    reference file, not directly from SKILL.md's own top level) contains a
    `### `-level heading anywhere in its body. `section()`'s boundary match
    is the bare `^### ` pattern, so such a heading — first line or not —
    would falsely terminate the enclosing phase's extraction — see Step 1.1
    of plans/test-improve-context-loading-strategy.md."""


def _reject_h3_heading_at_depth(
    target_text: str, depth: int, rel_path: str, source: str
) -> None:
    """Guard used by `_splice()`: a reference file included from inside
    another already-spliced-in reference file (`depth >= 1`) must not
    contain a `### `-level heading anywhere in its body — that level is
    reserved for phase boundaries and would falsely terminate `section()`'s
    extraction of the enclosing phase. Scans every line of `target_text`,
    not just the first — a `### ` heading further down in the body is just
    as fatal to `section()`'s extraction as one on the first line. No-op at
    `depth == 0` (a direct include from SKILL.md's own top level)."""
    if depth < 1:
        return
    for line in target_text.splitlines():
        if re.match(r"^### ", line):
            raise NestedHeadingLevelError(
                f"{rel_path}, included from {source} at depth {depth}, "
                f"contains a `### ` heading: {line!r}. Use `#### ` or "
                f"plain prose instead — `### ` is reserved for phase "
                f"boundaries and cannot appear anywhere in a file "
                f"included from another reference file."
            )


def _resolve_includes(
    text: str, depth: int, *, base: Path | None = None, source: str = "SKILL.md"
) -> str:
    """Recursively splice `<!-- include: references/<name>.md -->` marker
    lines in `text` with the referenced file's own (recursively resolved)
    content, in place of the marker line — a true in-place splice, never an
    append-at-end concatenation (the mechanism `section()`'s bounded,
    next-heading-terminated extraction depends on to recover spliced-in
    content).

    `depth` counts how many levels of include already led to `text`: `0`
    means `text` is SKILL.md's own body; `>= 1` means `text` came from a
    previously-resolved reference file. `base` is the directory
    `references/...` paths resolve against (defaults to test-improve's own
    skill directory); `source` names the file `text` came from, used only
    to identify the including file in error messages. See
    `resolve_test_improve_text()` below."""
    if depth > _MAX_INCLUDE_DEPTH:
        raise RecursionError(
            f"resolve_test_improve_text(): include recursion exceeded depth "
            f"{_MAX_INCLUDE_DEPTH} while resolving {source} — likely an "
            f"include cycle"
        )
    root = base if base is not None else SKILL_DIR

    def _splice(match: re.Match[str]) -> str:
        marker_line = match.group(0)
        rel_path = match.group(1)
        target = root / rel_path
        if not target.is_file():
            raise FileNotFoundError(
                f"resolve_test_improve_text(): {source} contains include marker "
                f"{marker_line!r} naming a target that does not exist: {target}"
            )
        target_text = target.read_text(encoding="utf-8")
        _reject_h3_heading_at_depth(target_text, depth, rel_path, source)
        return _resolve_includes(target_text, depth + 1, base=root, source=rel_path)

    return INCLUDE_RE.sub(_splice, text)


def resolve_test_improve_text() -> str:
    """Resolve every `<!-- include: references/*.md -->` marker in
    test-improve/SKILL.md, recursively, so content-guard tests can assert
    against the full combined text as if the skill had never been split.
    See Step 1.1 of plans/test-improve-context-loading-strategy.md.

    Named `resolve_test_improve_text`, not `test_improve_full_text`:
    importing a `test_`-prefixed name directly into a `test_*.py` module
    would make pytest mistake it for a test function (its name would match
    the default `test_*` collection pattern)."""
    return _resolve_includes(SKILL.read_text(encoding="utf-8"), depth=0)
