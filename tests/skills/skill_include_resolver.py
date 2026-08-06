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
import sys
from pathlib import Path

from skill_doc_helpers import PLUGIN_ROOT

SKILL_DIR = PLUGIN_ROOT / "skills" / "test-improve"
SKILL = SKILL_DIR / "SKILL.md"

# Import the marker grammar, recursion budget, and containment check from
# the shipped resolver instead of re-declaring them — a test module may
# import from plugin code (the reverse direction is what's forbidden; see
# build_knowledge_index.py's own comment on this). One owner for each means
# a future change can't silently drift the two implementations apart while
# every gate stays green — including the containment *algorithm* itself,
# not just the regex/depth constants: see `resolve_contained_target`'s own
# docstring for why it's shared rather than re-implemented here too.
_HOOKS_LIB = PLUGIN_ROOT / "hooks" / "lib"
if str(_HOOKS_LIB) not in sys.path:
    sys.path.insert(0, str(_HOOKS_LIB))

# The three `type: ignore[import-not-found]` below are all the same
# approved exception, not three separate ones: a static type-checker
# resolves imports from sys.path at analysis time, before the
# sys.path.insert() above has run, so it cannot see build_knowledge_index —
# a real module at runtime, just not on the checker's search path.
from build_knowledge_index import (  # type: ignore[import-not-found]
    INCLUDE_MARKER_RE as _MARKER_RE,
)
from build_knowledge_index import (  # type: ignore[import-not-found]
    MAX_INCLUDE_DEPTH as _MAX_INCLUDE_DEPTH,
)
from build_knowledge_index import (  # type: ignore[import-not-found]
    resolve_contained_target,
)

# Preserve _MARKER_RE's own flags (currently none beyond the implicit
# re.UNICODE) rather than assuming none exist — a future flag added to
# INCLUDE_MARKER_RE (e.g. re.VERBOSE) would otherwise silently not apply
# here, compiling the same pattern text under different semantics.
INCLUDE_RE = re.compile(_MARKER_RE.pattern, _MARKER_RE.flags | re.MULTILINE)


class NestedHeadingLevelError(Exception):
    """Raised by `_resolve_includes()` when any `references/*.md` file
    reached via an include marker — whether included directly from
    SKILL.md's own top level (depth 0) or from inside an already-spliced-in
    reference file (depth >= 1) — contains a `### `-level heading anywhere
    in its body. `section()`'s boundary match is the bare `^### ` pattern,
    so such a heading — first line or not — would falsely terminate the
    enclosing phase's extraction — see Step 1.1 of
    plans/test-improve-context-loading-strategy.md."""


def _reject_h3_heading(
    target_text: str, depth: int, rel_path: str, source: str
) -> None:
    """Guard used by `_splice()`: a reference file reached via an include
    marker — at any depth, including a direct include from SKILL.md's own
    top level — must not contain a `### `-level heading anywhere in its
    body. That level is reserved for phase boundaries and would falsely
    terminate `section()`'s extraction of the enclosing phase just as
    surely for a depth-0 target as for a nested one — every marker in
    SKILL.md sits inside a `### Phase N` section, so a `### ` heading added
    to a directly-included file truncates that section's extraction
    identically to the nested case. Scans every line of `target_text`, not
    just the first — a `### ` heading further down in the body is just as
    fatal to `section()`'s extraction as one on the first line."""
    for line in target_text.splitlines():
        if re.match(r"^### ", line):
            raise NestedHeadingLevelError(
                f"{rel_path}, included from {source} at depth {depth}, "
                f"contains a `### ` heading: {line!r}. Use `#### ` or "
                f"plain prose instead — `### ` is reserved for phase "
                f"boundaries and cannot appear anywhere in a file reached "
                f"via an include marker, at any depth."
            )


def _resolve_includes(
    text: str, depth: int, *, root: Path | None = None, source: str = "SKILL.md"
) -> str:
    """Recursively splice `<!-- include: references/<name>.md -->` marker
    lines in `text` with the referenced file's own (recursively resolved)
    content, in place of the marker line — a true in-place splice, never an
    append-at-end concatenation (the mechanism `section()`'s bounded,
    next-heading-terminated extraction depends on to recover spliced-in
    content).

    `depth` counts how many levels of include already led to `text`: `0`
    means `text` is SKILL.md's own body; `>= 1` means `text` came from a
    previously-resolved reference file. `root` is the directory
    `references/...` paths resolve against (defaults to test-improve's own
    skill directory) — named to match the shipped resolver's
    `_resolve_include_marker(body, root, depth)` parameter, not `base`.
    `source` names the file `text` came from, used only to identify the
    including file in error messages. See `resolve_test_improve_text()`
    below."""
    if depth > _MAX_INCLUDE_DEPTH:
        raise RecursionError(
            f"resolve_test_improve_text(): include recursion exceeded depth "
            f"{_MAX_INCLUDE_DEPTH} while resolving {source} — likely an "
            f"include cycle"
        )
    root = root if root is not None else SKILL_DIR

    def _splice(match: re.Match[str]) -> str:
        marker_line = match.group(0)
        rel_path = match.group(1)
        target = root / rel_path
        resolved_target = resolve_contained_target(target, root)
        if resolved_target is None:
            raise ValueError(
                f"resolve_test_improve_text(): {source} contains include marker "
                f"{marker_line!r} naming a target that is a symlink, escapes "
                f"the skill directory, or could not be resolved: {target}"
            )
        if not resolved_target.is_file():
            raise FileNotFoundError(
                f"resolve_test_improve_text(): {source} contains include marker "
                f"{marker_line!r} naming a target that does not exist: {target}"
            )
        target_text = resolved_target.read_text(encoding="utf-8")
        _reject_h3_heading(target_text, depth, rel_path, source)
        return _resolve_includes(target_text, depth + 1, root=root, source=rel_path)

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
