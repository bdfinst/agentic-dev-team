"""stub_extractors.go — Go `sc.Step(` registration: a top-level-only,
one-registration-per-call convention, distinct from the brace-balance
boundary the other three languages use. The registration call itself has no
brace-bounded body (its second argument is a bare function reference); the
referenced top-level `func` declaration's own brace-bounded body is looked
up separately to check for a pending marker.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ._common import (
    ERROR_DANGLING_ANNOTATION,
    ERROR_UNBALANCED_BRACES,
    ParseResult,
    StepBinding,
    extend_to_line_end,
    extract_first_string,
    extract_identifier,
    find_next_brace,
    is_pending,
    lexically_skip_to,
    scan_balanced,
)

_LANGUAGE = "Go"
_STEP_RE = re.compile(r"\bsc\.Step\s*\(")
_FUNC_DECL_RE = re.compile(r"\bfunc\s+([A-Za-z0-9_]+)\s*\(")


@dataclass
class _GoFuncBody:
    decl_start: int  # where 'func <name>(' itself begins — the declaration anchor
    start: int  # brace-bounded body start (for is_pending scanning)
    end: int  # brace-bounded body end, extended to its own line boundary
    error: str | None


def _index_func_decls(text: str) -> dict:
    """One-time pass over `text` collecting every top-level `func <name>(`
    declaration, keyed by name, as `{name: (decl_start, params_open)}`.
    Built once per `parse()` call so the per-binding lookup below is a dict
    lookup instead of re-searching the whole file from offset 0 for every
    `sc.Step(...)` registration found — the previous approach was
    O(bindings * file size) on a large Go file (issue #1421 bug 7). The
    first declaration of a given name wins; a duplicate is a Go compile
    error regardless of which one this index picks."""
    index: dict = {}
    for match in _FUNC_DECL_RE.finditer(text):
        name = match.group(1)
        if name not in index:
            index[name] = (match.start(), match.end() - 1)
    return index


def _bound_func_body(text: str, decl_start: int, params_open: int) -> _GoFuncBody:
    """Bound a known `func <name>(...) { ... }` declaration's parameter list
    and body via paren/brace balance, given positions already located by
    `_index_func_decls` (or a direct one-off regex search) — the balance-
    scanning logic shared by both the indexed (`parse`) and single-name
    (`find_scenario_initializer_body`) lookup paths."""
    params_close = scan_balanced(text, params_open, "(", ")", _LANGUAGE)
    if params_close is None:
        return _GoFuncBody(decl_start=decl_start, start=0, end=0, error=ERROR_UNBALANCED_BRACES)

    body_open = find_next_brace(text, params_close, len(text), _LANGUAGE)
    if body_open is None:
        return _GoFuncBody(decl_start=decl_start, start=0, end=0, error=ERROR_UNBALANCED_BRACES)
    body_close = scan_balanced(text, body_open, "{", "}", _LANGUAGE)
    if body_close is None:
        return _GoFuncBody(decl_start=decl_start, start=0, end=0, error=ERROR_UNBALANCED_BRACES)

    return _GoFuncBody(decl_start=decl_start, start=body_open, end=body_close, error=None)


def _find_func_body(text: str, func_name: str) -> _GoFuncBody | None:
    """Locate the top-level `func <func_name>(...) { ... }` declaration via a
    direct one-off regex search and return its brace-bounded body span plus
    its own declaration start. `None` means no such function was ever
    declared — the registration references nothing, i.e. dangling. Used
    only by `find_scenario_initializer_body` below — a single standalone
    lookup outside `parse()`'s main loop, where building a full index would
    be pure overhead; `parse()` itself uses `_index_func_decls` +
    `_bound_func_body` instead (issue #1421 bug 7)."""
    func_re = re.compile(r"\bfunc\s+" + re.escape(func_name) + r"\s*\(")
    match = func_re.search(text)
    if match is None:
        return None
    return _bound_func_body(text, match.start(), match.end() - 1)


# The conventional godog `ScenarioInitializer` entry-point function name
# (see knowledge/test-stack-profiles/bdd-frameworks.md's Go section and
# godog.TestSuite.ScenarioInitializer) — this plugin's own stub template
# always names it this. Used only as a fallback anchor by
# `find_scenario_initializer_body` below, for the "existing Go file with
# zero sc.Step(...) bindings yet" case (issue #1421 bug 1); the main `parse`
# loop above never assumes this name.
SCENARIO_INITIALIZER_NAME = "InitializeScenario"


def find_scenario_initializer_body(text: str) -> _GoFuncBody | None:
    """Public wrapper around `_find_func_body`, for callers outside this
    module (`gherkin_stub_merge.py`) that need to anchor a splice against
    the conventional `InitializeScenario(sc *godog.ScenarioContext)`
    registration function directly, when there are no existing `sc.Step(...)`
    bindings to anchor against instead."""
    return _find_func_body(text, SCENARIO_INITIALIZER_NAME)


def parse(text: str, markers: tuple) -> ParseResult:
    bindings = []
    pos = 0
    n = len(text)
    func_index = _index_func_decls(text)  # one pass, not one per binding (bug 7)
    while pos < n:
        match = _STEP_RE.search(text, pos)
        if match is None:
            break
        start = match.start()
        landed = lexically_skip_to(text, pos, start, _LANGUAGE)
        if landed > start:
            pos = landed
            continue

        call_open = match.end() - 1
        call_end = scan_balanced(text, call_open, "(", ")", _LANGUAGE)
        if call_end is None:
            return ParseResult(bindings=None, error=ERROR_UNBALANCED_BRACES)

        pattern, pattern_end = extract_first_string(text, call_open + 1, call_end, _LANGUAGE)
        func_name = extract_identifier(text, pattern_end, call_end)
        if not func_name:
            return ParseResult(bindings=None, error=ERROR_DANGLING_ANNOTATION)

        func_entry = func_index.get(func_name)
        if func_entry is None:
            # The registration names a function that was never declared —
            # a marker with no attached, boundable body.
            return ParseResult(bindings=None, error=ERROR_DANGLING_ANNOTATION)
        func_result = _bound_func_body(text, *func_entry)
        if func_result.error is not None:
            return ParseResult(bindings=None, error=func_result.error)

        body_text = text[func_result.start : func_result.end]
        end = call_end
        if end < n and text[end] == ";":
            end += 1
        end = extend_to_line_end(text, end)

        # The referenced function's own declaration lives at a different,
        # non-adjacent position than the registration call (start:end) —
        # captured separately so a caller reusing this binding as new
        # candidate content (gherkin_stub_merge.merge_steps) can insert the
        # declaration and the registration at their two correct positions
        # instead of silently dropping the declaration.
        decl_end_line = extend_to_line_end(text, func_result.end)
        bindings.append(
            StepBinding(
                pattern=pattern,
                text=text[start:end],
                start=start,
                end=end,
                is_pending=is_pending(body_text, markers),
                decl_start=func_result.decl_start,
                decl_text=text[func_result.decl_start : decl_end_line],
            )
        )
        pos = end

    return ParseResult(bindings=bindings, error=None)
