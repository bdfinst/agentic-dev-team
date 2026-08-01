"""stub_extractors — per-language step-definition binding extractors for
`gherkin_stub_merge.py` (issue #1421).

A step-definition file is arbitrary general-purpose source code, unlike a
`.feature` file's fixed, line-anchored Gherkin grammar — so "next marker line
is the boundary" (the approach `gherkin_feature_merge.py` can safely use) is
not safe here. Each binding's body must instead be bounded by an actual
lexical scan of the source: brace/paren balance for JS/TS, Java, and C#
(`jsts.py`/`java.py`/`csharp.py`), or — for Go, which registers a step via a
single `sc.Step(pattern, funcName)` call referencing a separately-declared
top-level function — a lookup of that referenced function's own
brace-bounded body (`go.py`).

The brace/paren balance count is **lexically aware**, not a naive character
count: a `(`/`)`/`{`/`}` occurring inside a string/char literal or a
line/block comment is skipped, not counted (`_common.py`), so a step body
containing `const s = "}";` (or the C#/Go string-literal equivalents) can
never be mistaken for a boundary. When a file's brackets genuinely don't
balance, or a marker (a call, annotation, or attribute) has no attached,
boundable body, `parse_existing_steps` returns a structural-error sentinel
(`unbalanced-braces` / `dangling-annotation`) rather than guessing a span —
refusing the write is the safety property this package exists to provide.

Started as a single flat `_stub_extractors.py` module; split into this
sub-package once the single-file draft passed the ~300-line size ceiling
(plan-review structure finding) — one file per language plus one shared
lexer module keeps each file's responsibility narrow, rather than
reproducing `gherkin_feature_merge.py`'s five-plus-responsibility sprawl one
import hop down.

Reuses `lib._bdd_markers.MARKERS_BY_EXT` for the per-language pending-marker
table (extension -> (language label, marker substrings)) rather than
re-deriving it — a lib-level sibling import, not a reach into the parent
`scripts/` entry-point layer (issue #1421 bug 5: this package used to import
`gherkin_stub_gate`'s module-private `_MARKERS_BY_EXT` via a `sys.path`
insertion reaching up to `scripts/`, the only module under `scripts/lib/` in
the repo that imported from that parent layer).

Stdlib-only. (ADR 0014/0015).
"""

from __future__ import annotations

from _bdd_markers import MARKERS_BY_EXT as _PENDING_MARKERS_BY_EXT

from . import csharp, go, java, jsts
from ._common import (
    ERROR_DANGLING_ANNOTATION,
    ERROR_UNBALANCED_BRACES,
    ParseResult,
    StepBinding,
)

__all__ = [
    "ERROR_DANGLING_ANNOTATION",
    "ERROR_UNBALANCED_BRACES",
    "ParseResult",
    "StepBinding",
    "parse_existing_steps",
]

_PARSERS_BY_LANGUAGE = {
    "JS/TS": jsts.parse,
    "Java": java.parse,
    "C#": csharp.parse,
    "Go": go.parse,
}


def parse_existing_steps(text: str, ext: str) -> ParseResult:
    """Parse every step-definition binding in `text` for the language
    implied by `ext` (matched case-insensitively, reusing
    `lib._bdd_markers.MARKERS_BY_EXT`). Returns `ParseResult(bindings=[...],
    error=None)` on success, or `ParseResult(bindings=None, error=<sentinel>)`
    on the first structural problem encountered — never a partial, possibly-
    wrong result."""
    entry = _PENDING_MARKERS_BY_EXT.get(ext.lower())
    if entry is None:
        raise ValueError(f"unsupported step-definition extension: {ext!r}")
    language, markers = entry
    parser = _PARSERS_BY_LANGUAGE[language]
    return parser(text, markers)
