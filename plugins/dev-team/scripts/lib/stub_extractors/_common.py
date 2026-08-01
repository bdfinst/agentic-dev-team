"""stub_extractors._common — shared lexical-scanning primitives, the two
structural-error sentinels, and the dataclasses every per-language extractor
in this package returns.

Hoisted out of a single `_stub_extractors.py` once that file grew past the
~300-line size ceiling (plan-review structure finding) — one shared module
plus one file per language keeps each file's responsibility narrow, mirroring
how `_vendored_tree.py` and `_gherkin_text.py` were already extracted from
their own call sites once a second/third occurrence appeared.

Stdlib-only. (ADR 0014/0015).
"""

from __future__ import annotations

from dataclasses import dataclass

# The two structural-error sentinels every extractor (and gherkin_stub_merge.py
# itself) shares — named once so call sites and tests reference the constant,
# never a repeated raw literal.
ERROR_UNBALANCED_BRACES = "unbalanced-braces"
ERROR_DANGLING_ANNOTATION = "dangling-annotation"


@dataclass
class StepBinding:
    """One parsed step-definition binding: its step-pattern text, the full
    bounded verbatim source span (`text[start:end]`), and whether its body
    contains a pending marker.

    `decl_start`/`decl_text` are Go-only (`None` for JS/TS, Java, C#, where
    the callback/method body is adjacent to the call/annotation, so
    `text[start:end]` already captures everything). Go's registration
    (`sc.Step(pattern, funcName)`) and the `funcName` function it references
    are non-adjacent source regions — `decl_start` is where that referenced
    function's own declaration begins, and `decl_text` is its full verbatim
    source. Without these, reusing `text` as a new candidate's insertable
    content silently drops the function declaration a Go step needs to
    compile (bug caught by this module's own runtime CLI verification,
    fixed here rather than shipped)."""

    pattern: str
    text: str
    start: int  # char offset into the parsed text, inclusive
    end: int  # char offset, exclusive — always a line boundary (see extend_to_line_end)
    is_pending: bool
    decl_start: int | None = None
    decl_text: str | None = None


@dataclass
class ParseResult:
    bindings: list | None
    error: str | None


# ---------------------------------------------------------------------------
# Shared lexical scanning — string/char-literal/comment awareness so brace and
# paren counting never miscounts a bracket embedded in either.
# ---------------------------------------------------------------------------


def skip_quoted(text: str, i: int, quote: str) -> int:
    """`text[i] == quote`. Return the index just past the matching unescaped
    closing `quote` (backslash-escaping honored), or `len(text)` if the
    string never closes before EOF."""
    j = i + 1
    n = len(text)
    while j < n:
        if text[j] == "\\":
            j += 2
            continue
        if text[j] == quote:
            return j + 1
        j += 1
    return n


def skip_verbatim_string(text: str, i: int) -> int:
    """`text[i:i+2] == '@\"'` (a C# verbatim string). A doubled `\"\"` inside
    is an escaped quote, not the terminator — distinct from `skip_quoted`'s
    backslash-escaping rule."""
    j = i + 2
    n = len(text)
    while j < n:
        if text[j] == '"':
            if j + 1 < n and text[j + 1] == '"':
                j += 2
                continue
            return j + 1
        j += 1
    return n


def skip_regex_literal(text: str, i: int) -> int:
    """`text[i] == '/'` starting a JS/TS regex literal (e.g.
    `/^I have (\\d+) cukes$/`) — a real, common cucumber-js step-pattern
    convention alongside a quoted string. Return the index just past the
    matching unescaped closing `/` (backslash-escaping honored, mirroring
    `skip_quoted`), or `len(text)` if it never closes. Only called from
    `extract_first_string` at a pattern-argument position, where a leading
    `/` unambiguously starts a regex literal (comments are `//`/`/*`,
    already dispatched to `skip_lexical_token` before this is ever
    reached)."""
    j = i + 1
    n = len(text)
    while j < n:
        if text[j] == "\\":
            j += 2
            continue
        if text[j] == "/":
            return j + 1
        j += 1
    return n


def skip_lexical_token(text: str, i: int, language: str) -> int | None:
    """If a string/char literal or comment starts at `text[i]`, return the
    index just past its end. Otherwise `None` — `text[i]` is ordinary code
    and should be scanned normally."""
    ch = text[i]
    nxt = text[i + 1] if i + 1 < len(text) else ""

    if ch == "/" and nxt == "/":
        end = text.find("\n", i)
        return len(text) if end == -1 else end
    if ch == "/" and nxt == "*":
        end = text.find("*/", i + 2)
        return len(text) if end == -1 else end + 2
    if language == "C#" and ch == "@" and nxt == '"':
        return skip_verbatim_string(text, i)
    if language == "Go" and ch == "`":
        j = text.find("`", i + 1)
        return len(text) if j == -1 else j + 1
    if language == "JS/TS" and ch == "`":
        return skip_quoted(text, i, "`")
    if ch == '"':
        return skip_quoted(text, i, '"')
    if ch == "'":
        return skip_quoted(text, i, "'")
    return None


def scan_balanced(text: str, open_idx: int, open_ch: str, close_ch: str, language: str) -> int | None:
    """`text[open_idx] == open_ch`. Scan forward tracking `open_ch`/`close_ch`
    depth, skipping any lexical token (string/char literal/comment)
    encountered along the way. Return the index just past the matching
    `close_ch`, or `None` if depth never returns to zero before EOF —
    the file's brackets don't lexically balance."""
    depth = 0
    i = open_idx
    n = len(text)
    while i < n:
        skip_to = skip_lexical_token(text, i, language)
        if skip_to is not None:
            i = skip_to
            continue
        ch = text[i]
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return None


def find_next_brace(text: str, start: int, limit: int, language: str) -> int | None:
    """Return the index of the next `{` in `text[start:limit]` that is not
    inside a string/char literal or comment, or `None` if none precedes
    `limit`."""
    i = start
    while i < limit:
        skip_to = skip_lexical_token(text, i, language)
        if skip_to is not None:
            i = skip_to
            continue
        if text[i] == "{":
            return i
        i += 1
    return None


def lexically_skip_to(text: str, pos: int, target: int, language: str) -> int:
    """Scan forward from `pos` (assumed to be ordinary-code position) to
    `target`, skipping any string/char literal/comment encountered. Returns
    a position >= `target`; a result strictly greater than `target` means
    `target` sat *inside* a skipped token — e.g. a marker-like substring
    appearing in a string or comment, which must not be mistaken for a real
    binding boundary."""
    i = pos
    while i < target:
        skip_to = skip_lexical_token(text, i, language)
        if skip_to is not None:
            i = skip_to
            continue
        i += 1
    return i


def extend_to_line_end(text: str, idx: int) -> int:
    """Return an index >= `idx` landing just past the next newline at or
    after `idx`, or `len(text)` if none remains — so a binding's span always
    ends at a line boundary, giving `gherkin_stub_merge.py` a clean splice
    point for appending new stubs."""
    nl = text.find("\n", idx)
    return len(text) if nl == -1 else nl + 1


def extract_first_string(text: str, start: int, limit: int, language: str) -> tuple:
    """Scan `text[start:limit]` for the first string or (JS/TS only) regex
    literal (skipping any comment encountered first) and return
    `(pattern_text, end_index)` — the dequoted/de-slashed contents and the
    index just past the closing delimiter. Returns `("", start)` if neither
    is found before `limit`.

    A JS/TS regex-literal pattern (`Given(/^I have (\\d+) cukes$/, ...)`,
    a real cucumber-js convention) is not a quoted string at all — without
    explicit recognition here it falls through to the `("", start)` no-match
    case, recording an empty pattern. Since `merge_steps` dedups by exact
    pattern-text match, an empty string can never match anything, so an
    already-implemented regex-pattern step gets a duplicate pending stub
    appended on every re-run (issue #1421 bug 4 — the clobber-equivalent
    this module exists to prevent, for one pattern syntax)."""
    i = start
    while i < limit:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if ch == "/" and nxt in ("/", "*"):
            skip_to = skip_lexical_token(text, i, language)
            i = skip_to if skip_to is not None else i + 1
            continue
        is_verbatim = language == "C#" and ch == "@" and nxt == '"'
        is_regex_literal = language == "JS/TS" and ch == "/"
        is_string_start = (
            is_verbatim
            or is_regex_literal
            or ch in ("'", '"')
            or (ch == "`" and language in ("JS/TS", "Go"))
        )
        if is_string_start:
            end = skip_regex_literal(text, i) if is_regex_literal else skip_lexical_token(text, i, language)
            quote_len = 2 if is_verbatim else 1
            return text[i + quote_len : end - 1], end
        i += 1
    return "", start


def extract_identifier(text: str, start: int, limit: int) -> str:
    """Skip leading whitespace/commas from `start`, then read an
    identifier (`[A-Za-z0-9_]+`). Returns `""` if none found immediately."""
    i = start
    while i < limit and text[i] in " \t\r\n,":
        i += 1
    j = i
    while j < limit and (text[j].isalnum() or text[j] == "_"):
        j += 1
    return text[i:j]


def is_pending(body_text: str, markers: tuple) -> bool:
    return any(marker in body_text for marker in markers)


def build_binding(
    text: str, start: int, pattern: str, body_start: int, body_end: int, markers: tuple
) -> tuple:
    """Construct a `StepBinding` once a binding's brace-bounded body span
    `[body_start, body_end)` has been located, and return `(binding,
    next_pos)` — `next_pos` is where the caller's scan should resume.
    Identical across all three parse functions (`jsts.py`, `parse_annotation_
    style`, `go.py`), hoisted here rather than repeated three times."""
    body_text = text[body_start:body_end]
    end = extend_to_line_end(text, body_end)
    binding = StepBinding(
        pattern=pattern,
        text=text[start:end],
        start=start,
        end=end,
        is_pending=is_pending(body_text, markers),
    )
    return binding, end


def parse_annotation_style(text: str, markers: tuple, language: str, annotation_re) -> ParseResult:
    """Shared control flow for Java's `@Given(`/`@When(`/`@Then(` annotation
    and C#'s `[Given(`/`[When(`/`[Then(` attribute (`java.py`/`csharp.py`) —
    both bind a step to the *next* method's brace-bounded body, differing
    only in the marker syntax (`annotation_re`) and the per-language lexer
    profile (`language`, for C#'s verbatim-string awareness). Factored out
    once the two extractors turned out identical apart from that one regex
    (structure-review: semantic, not just structural, duplication)."""
    bindings = []
    pos = 0
    n = len(text)
    while pos < n:
        match = annotation_re.search(text, pos)
        if match is None:
            break
        start = match.start()
        landed = lexically_skip_to(text, pos, start, language)
        if landed > start:
            pos = landed
            continue

        ann_open = match.end() - 1
        ann_close = scan_balanced(text, ann_open, "(", ")", language)
        if ann_close is None:
            return ParseResult(bindings=None, error=ERROR_UNBALANCED_BRACES)

        pattern, _pattern_end = extract_first_string(text, ann_open + 1, ann_close, language)

        next_match = annotation_re.search(text, ann_close)
        search_limit = next_match.start() if next_match else n
        brace_open = find_next_brace(text, ann_close, search_limit, language)
        if brace_open is None:
            # No method body found before the next annotation (or EOF) — a
            # dangling annotation, not an unbalanced count.
            return ParseResult(bindings=None, error=ERROR_DANGLING_ANNOTATION)
        brace_close = scan_balanced(text, brace_open, "{", "}", language)
        if brace_close is None:
            return ParseResult(bindings=None, error=ERROR_UNBALANCED_BRACES)

        binding, pos = build_binding(text, start, pattern, brace_open, brace_close, markers)
        bindings.append(binding)

    return ParseResult(bindings=bindings, error=None)
