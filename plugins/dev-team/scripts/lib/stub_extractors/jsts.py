"""stub_extractors.jsts — JS/TS `Given(`/`When(`/`Then(` call-style step
bindings, callback body bounded by lexically-aware brace balance.

Known scope limitation (self-identified, correctness-review lens): this
extractor assumes the convention `gherkin-derive/SKILL.md` Step 4 and
`gherkin_stub_gate.py`'s own pending-marker table both assume — an inline
callback literal (`function () { ... }` or `() => { ... }`) as the second
argument. A step bound to a *named* function reference (`Given('x',
stepImpl);`, no inline braces) has no brace-bounded body for this extractor
to find, and is reported as `dangling-annotation` (a marker with no
attached, boundable body — the same sentinel `go.py` and
`_common.parse_annotation_style` use for their equivalent case), not
`unbalanced-braces` — the file's braces genuinely balance; there is simply
no callback to bound. Out of scope for this module's stated design
(brace-balance bounding), not silently mishandled — noted here rather than
guessed around.

The callback's own parameter list is always located and skipped via paren
balance *before* searching for its body brace, so a destructured parameter
(`({ page }) => { ... }`) is never mistaken for the body — the destructure's
own `{`/`}` pair sits inside the parameter list's parens, which paren
balance clears in one step regardless of what braces it contains
(issue #1421 bug 3).
"""

from __future__ import annotations

import re

from ._common import (
    ERROR_DANGLING_ANNOTATION,
    ERROR_UNBALANCED_BRACES,
    ParseResult,
    build_binding,
    extract_first_string,
    find_next_brace,
    lexically_skip_to,
    scan_balanced,
    skip_lexical_token,
)

_LANGUAGE = "JS/TS"
_KEYWORD_RE = re.compile(r"\b(?:Given|When|Then)\s*\(")


def _find_next_paren(text: str, start: int, limit: int, language: str) -> int | None:
    """Return the index of the next `(` in `text[start:limit]` that is not
    inside a string/char literal or comment, or `None` if none precedes
    `limit`. Used to locate a callback's own parameter list — its opening
    paren — so it can be fully skipped via paren balance (see `parse`
    below) before searching for the callback's real body brace."""
    i = start
    while i < limit:
        skip_to = skip_lexical_token(text, i, language)
        if skip_to is not None:
            i = skip_to
            continue
        if text[i] == "(":
            return i
        i += 1
    return None


def parse(text: str, markers: tuple) -> ParseResult:
    bindings = []
    pos = 0
    n = len(text)
    while pos < n:
        match = _KEYWORD_RE.search(text, pos)
        if match is None:
            break
        start = match.start()
        landed = lexically_skip_to(text, pos, start, _LANGUAGE)
        if landed > start:
            pos = landed
            continue

        call_open = match.end() - 1  # the '(' the regex matched up to
        call_end = scan_balanced(text, call_open, "(", ")", _LANGUAGE)
        if call_end is None:
            return ParseResult(bindings=None, error=ERROR_UNBALANCED_BRACES)

        pattern, pattern_end = extract_first_string(text, call_open + 1, call_end, _LANGUAGE)

        # Locate the callback's own parameter list first (its opening '(')
        # and skip past it via paren balance before searching for the
        # callback's real body brace. A destructured parameter
        # (`({ page }) => { ... }`) has its own '{'/'}' pair *inside* that
        # parameter list — searching for "the first '{' after the pattern"
        # (the previous approach) finds the destructure's brace instead of
        # the body, mis-binding the span onto a few characters of parameter
        # syntax rather than the real callback (issue #1421 bug 3: a
        # silent-corruption risk — a subsequent merge could splice a new
        # stub into the middle of this existing callback body). Paren
        # balance ignores nested braces entirely, so this correctly clears
        # the whole parameter list — destructured or not — regardless of
        # whether the callback is `function (...) { ... }` or an arrow.
        param_open = _find_next_paren(text, pattern_end, call_end, _LANGUAGE)
        if param_open is None:
            # No callback signature at all between the pattern and the
            # call's own closing paren — e.g. a named-function reference
            # (`Given('x', stepImpl);`). The file's braces balance fine;
            # there's simply no attached body to bound.
            return ParseResult(bindings=None, error=ERROR_DANGLING_ANNOTATION)
        param_close = scan_balanced(text, param_open, "(", ")", _LANGUAGE)
        if param_close is None or param_close > call_end:
            return ParseResult(bindings=None, error=ERROR_UNBALANCED_BRACES)

        brace_open = find_next_brace(text, param_close, call_end, _LANGUAGE)
        if brace_open is None:
            # No block body follows the callback's own parameter list —
            # e.g. an expression-bodied arrow (`() => doSomething()`).
            # Refuse to guess a span rather than risk mis-splicing.
            return ParseResult(bindings=None, error=ERROR_DANGLING_ANNOTATION)
        brace_close = scan_balanced(text, brace_open, "{", "}", _LANGUAGE)
        if brace_close is None or brace_close > call_end:
            return ParseResult(bindings=None, error=ERROR_UNBALANCED_BRACES)

        # build_binding extends to the next line boundary from brace_close,
        # which already carries the call's own closing ')' and any trailing
        # ';' along with it for the common single-line-close convention
        # (`});`) — no separate call-tail handling needed.
        binding, pos = build_binding(text, start, pattern, brace_open, brace_close, markers)
        bindings.append(binding)

    return ParseResult(bindings=bindings, error=None)
