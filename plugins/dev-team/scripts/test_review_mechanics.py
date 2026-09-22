#!/usr/bin/env python3
"""Mechanical pre-phase for `agents/test-review.md` (#2169 Step 2.2).

`test-review.md` (Step 2.1, #2169) annotates each of its own `## Detect`
checks as `[MECHANICAL]` (an explicit per-language detection signature or
grep/threshold rule) or `[JUDGMENT]` (requires semantic reasoning about
intent). This script computes every `[MECHANICAL]` check that is cheap to
run as a script, for one test file at a time, so the agent cites raw counts
instead of re-deriving them in prose:

- tests with no assertion call — `error` (matches test-review.md's Severity
  Anchors table)
- missing `await` on async test bodies (JS/TS/C#/Java) — `warning`
- mocks/stubs created without a reset/clear call, or a same-shaped
  re-instantiation/re-initialization in `[SetUp]`/`[TestInitialize]`/
  `@BeforeEach`/`@BeforeAll`, in the same file — `warning`
- unstubbed clock/RNG/timer access (JS/TS/C#/Java), suppressed when a
  fake-timer/injected-clock marker (`jest.useFakeTimers()`, an injected
  `IClock`/`TimeProvider`, `Clock.fixed`, ...) is present in the same
  file — `warning`
- reflection into private members as primary test strategy (Java/C#/
  Python/JS/TS) — `warning`, NOT promoted to `error` by this migration
- the Tolerated-Deviation Hunt's >=3-artifact consolidation rule, with a
  cheap same-line/adjacent-line ticket-reference qualifier suppressing the
  disabled-test/aged-marker/suppressed-warning categories — `warning`

Test-region boundaries (the `it()`/`test()` call for JS/TS, the annotated
method for C#/Java) are found by depth-counting over a MASKED copy of the
file (`_mask_code`) with string/template/char literals and comments blanked
out first — a stray `)`/`(`/`{`/`}` inside a title, comment, or string body
can no longer early-close a region or drive the balance past EOF. For JS/TS,
the no-assertion and missing-await checks additionally never see the
description-string argument itself — `_js_content_slice` derives a
callback-only CONTENT slice from the boundary-only region, so a title like
`'should render'` or `'awaits the response'` can never satisfy the
assertion/await keyword search on its own words (see `_GATING_CATEGORIES`
below for why this specifically matters: no-assertion is one of the two
categories that sets `mechanicalFail`).

Internal-collaborator-doubling detection is NOT reimplemented here — it is
reused via subprocess against `skills/test-design/scripts/
internal_double_detector.py`, whose own docstring documents `--files` as
the seam built for exactly this kind of caller (the subprocess call itself
goes through an injectable `double_detector_runner` parameter so unit tests
for unrelated checks can stub it out rather than paying real spawn cost).
That detector has no `severity` field; its findings carry a `verdict` of
`"high"`, `"informational"`, or `"advisory"`. Only `verdict == "high"` is
translated here into this script's own `error`-severity finding — never a
literal `severity == "error"` check against the reused script's raw JSON,
since no such field exists there.

Two disclosure gaps are surfaced explicitly rather than failing open to a
plain clean bill:

- `internal_double_detector.py`'s own `analyze()` only scans files under a
  `test`/`tests` path segment — narrower than this repo's own test-file
  conventions (`*.test.*`, `*.spec.*`, `__tests__/`, see
  `knowledge/test-file-indicators.md`). When the analyzed file's path has
  no `test`/`tests` segment, the doubling check never runs for it; this
  script emits a named `internal-collaborator-doubling-out-of-scope`
  finding instead of silently reporting zero doubling findings.
- A subprocess spawn/timeout failure or invalid-JSON response from the
  detector is reported as `internal-collaborator-doubling-unavailable` at
  `warning` severity (raised from `suggestion` — a run that never happened
  must not read the same as a clean pass).

Both gaps also set the top-level `doublingCheckRan: false` key so a
downstream consumer can distinguish "mechanically clean except the doubling
gate, which did not run" from a plain clean bill.

`mechanicalFail` is `true` ONLY when a no-assertion-test finding is present
OR a translated `internal-collaborator-doubling` `error` finding is
present. Every other finding this script emits is `warning`-severity: it is
reported, with counts, but never gates the qualitative pass on its own.

A file this script cannot decode/parse produces a single `parse-failure`
finding (no severity that participates in `mechanicalFail`) and falls
through as mechanically clean — this script never crashes and never
silently drops a file.

This script does NOT own an ambient-API marker table of its own for
`internal_double_detector.py`'s B2-waiver-evidence purpose — that table
(`_AMBIENT_API_MARKERS` in that module) stays there; see the REFACTOR note
at `_CLOCK_RNG_TIMER_MARKERS` below for why this script's own marker table
is a different list, not a duplicate.

The Tolerated-Deviation Hunt (`_check_tolerated_deviation`) runs against
whichever single file the CLI is given, test or non-test — it does NOT
restrict itself to "core-flow, non-test source" the way `test-review.md`'s
prose scopes the hunt. Resolving that scoping gap (which files this check
should actually run against) is deferred to Step 2.3's wiring of this
script into test-review's protocol; this script's own per-file CLI shape
is unopinionated about which files it's called with.

Stdlib-only (ADR 0014/0015). See docs/python-hook-contract.md.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

#: `internal_double_detector.py` lives under `skills/test-design/scripts/`;
#: this script lives under `scripts/` — both are children of the plugin
#: root (`plugins/dev-team/`), so `parents[1]` from this file reaches it.
_DETECTOR_PATH = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "test-design"
    / "scripts"
    / "internal_double_detector.py"
)

LANG_BY_EXT: dict[str, str] = {
    ".py": "python",
    ".js": "js_ts",
    ".jsx": "js_ts",
    ".mjs": "js_ts",
    ".cjs": "js_ts",
    ".ts": "js_ts",
    ".tsx": "js_ts",
    ".cs": "csharp",
    ".java": "java",
}

CONSOLIDATION_THRESHOLD = 3

#: "No specific line available" sentinel — used for parse-failure/decode
#: findings and translated-detector findings with no line info of their own.
_UNKNOWN_LINE = 1

#: Passed as `timeout=` to the `internal_double_detector.py` subprocess call.
_DOUBLE_DETECTOR_TIMEOUT_SECONDS = 60

#: `test`/`tests` path-segment names — mirrors `internal_double_detector.py`'s
#: own `_TEST_DIR_NAMES`/`_is_test_tree` scoping exactly (this is a
#: disclosure check on top of that scoping, not a reimplementation of the
#: detector itself — see the module docstring's out-of-scope paragraph).
_TEST_DIR_NAMES = frozenset({"test", "tests"})

# --- Generic assertion-call detector -----------------------------------------

#: "no Assert, expect, should, verify, or equivalent assertion call" —
#: test-review.md's own generic (language-agnostic) wording for the
#: no-assertion check.
_ASSERTION_RE = re.compile(r"\b(assert\w*|expect|should\w*|verify\w*)\b", re.IGNORECASE)


# --- Test-region extraction (brace/paren-balanced, per language) ------------

#: Matches a plain `it(`/`test(` call (with optional `.only`/`.skip`) as
#: well as an `it.each(<table>)(`/`test.each(<table>)(` parameterized-table
#: call — group 1 always captures the FINAL call's own opening paren (the
#: description+callback call), never the `.each` table's paren, so
#: extraction downstream is identical for both forms. The `.each(...)`
#: table itself may contain one level of nested parens (e.g. a function
#: call inside the table) but no more — a reasonable approximation of the
#: common forms, not a full parser.
_JS_TEST_CALL_RE = re.compile(
    r"\b(?:it|test)(?:\.only|\.skip)?"
    r"(?:\.each\s*\((?:[^()]|\([^()]*\))*\))?"
    r"\s*(\()"
)
_JS_ASYNC_CALLBACK_RE = re.compile(r"^\(\s*['\"`][^'\"`]*['\"`]\s*,\s*async\b")

_CSHARP_TEST_ATTR_RE = re.compile(
    r"^[ \t]*\[(?:Test|Fact|TestMethod|Theory|TestCase|TestCaseSource)(?:\([^\]]*\))?\]",
    re.MULTILINE,
)
_JAVA_TEST_ANNOT_RE = re.compile(r"^[ \t]*@(?:Test|ParameterizedTest)\b", re.MULTILINE)
_PY_TEST_DEF_RE = re.compile(r"^([ \t]*)(?:async\s+)?def\s+(test_\w+)\s*\(", re.MULTILINE)

#: Setup/init method markers — used only by `_mock_reinitialized` (Fix 4) to
#: find a `[SetUp]`/`[TestInitialize]`/`@BeforeEach`/`@BeforeAll` method's
#: own body, never treated as a test method for any other check.
_CSHARP_SETUP_ATTR_RE = re.compile(r"^[ \t]*\[(?:SetUp|TestInitialize)\]", re.MULTILINE)
_JAVA_SETUP_ANNOT_RE = re.compile(r"^[ \t]*@(?:BeforeEach|BeforeAll)\b", re.MULTILINE)
_SETUP_ANNOT_RE: dict[str, re.Pattern] = {"csharp": _CSHARP_SETUP_ATTR_RE, "java": _JAVA_SETUP_ANNOT_RE}

_CSHARP_ASYNC_TASK_RE = re.compile(r"\basync\s+Task\b")
_JAVA_FUTURE_TYPE_RE = re.compile(r"\b(?:Future|CompletableFuture)\b")
_JAVA_FUTURE_RESOLVED_RE = re.compile(r"\.(?:get|join)\s*\(")


class ParseFailure(Exception):
    """A test-region boundary (parens/braces) never closed before EOF.

    Raised internally by the region-extraction helpers and caught once, at
    the top of `analyze_file`, which turns it into a `parse-failure`
    finding — this exception must never propagate out of `analyze_file`."""


def _line_no(text: str, idx: int) -> int:
    return text.count("\n", 0, idx) + 1


def _mask_code(text: str) -> str:
    """Same-length copy of `text` with string/template/char literals and
    `//`/`/* */` comments blanked to spaces (newlines preserved), so
    paren/brace depth-counting and top-level-comma scanning never trip on
    a stray `)`/`(`/`{`/`}`/`,` sitting inside a title, comment, or string
    body (Fix 1). Character offsets and line numbers are identical to
    `text` — callers index into the ORIGINAL text using positions computed
    against this masked copy.

    Limitation: a JS/TS template literal's `${...}` interpolation is
    masked along with the rest of the template, not treated as live code —
    blanket-masking the whole template is the safer default (a stray brace
    inside an interpolation could otherwise miscount), at the cost of not
    recognizing real code inside `${}`. Out of scope for this fix pass."""
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        two = text[i : i + 2]
        if two == "//":
            j = i
            while j < n and text[j] != "\n":
                out[j] = " "
                j += 1
            i = j
        elif two == "/*":
            end = text.find("*/", i + 2)
            j_end = end + 2 if end != -1 else n
            for j in range(i, j_end):
                if text[j] != "\n":
                    out[j] = " "
            i = j_end
        elif text[i] in ("'", '"', "`"):
            quote = text[i]
            out[i] = " "
            j = i + 1
            while j < n:
                if text[j] == "\\" and j + 1 < n:
                    if text[j] != "\n":
                        out[j] = " "
                    if text[j + 1] != "\n":
                        out[j + 1] = " "
                    j += 2
                    continue
                closing = text[j] == quote
                if text[j] != "\n":
                    out[j] = " "
                j += 1
                if closing:
                    break
            i = j
        else:
            i += 1
    return "".join(out)


def _matching_close_index(text: str, masked: str, open_idx: int, open_ch: str, close_ch: str) -> int | None:
    """Index into `text` of the character matching `text[open_idx]` (which
    must be `open_ch`), found by depth-counting over `masked` (same length
    as `text`, string/template/char literals and comments already blanked
    there — Fix 1). Returns `None` if depth never returns to 0 before EOF."""
    depth = 0
    i = open_idx
    n = len(masked)
    while i < n:
        c = masked[i]
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def _js_content_slice(region: str, masked_region: str) -> str:
    """Slice of `region` (a full `it()`/`test()` call region, its own
    parens included) starting just after the description-string
    argument's closing quote and the following top-level comma — the
    callback argument only, title/description stripped out (Fix 1:
    `_check_no_assertion`/`_check_missing_await` must never match a
    keyword sitting in the title itself, e.g. `'should render'` or
    `'awaits the response'`). Falls back to the full `region` when no
    leading string-literal argument is found (e.g. an `it(name, fn)` form
    using a variable title) or no top-level comma follows it."""
    n = len(region)
    j = 1
    while j < n and region[j] in " \t\r\n":
        j += 1
    if j >= n or region[j] not in "'\"`":
        return region
    quote = region[j]
    end = j + 1
    closed = False
    while end < n:
        if region[end] == "\\" and end + 1 < n:
            end += 2
            continue
        if region[end] == quote:
            end += 1
            closed = True
            break
        end += 1
    if not closed:
        return region
    depth = 0
    k = end
    while k < n:
        c = masked_region[k]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                return region
            depth -= 1
        elif c == "," and depth == 0:
            return region[k + 1 :]
        k += 1
    return region


def _js_ts_test_regions(text: str, masked: str) -> list[dict]:
    """`{"line", "is_async", "content"}` for each `it()`/`test()` call
    (including `.each` parameterized-table forms) — shared by
    `_check_no_assertion` and `_check_missing_await` (Fix 11) so the
    region/content boundaries are computed exactly once per file.
    `is_async` is read off the FULL region (it needs the title text
    structurally present to match); `content` is the title-stripped
    slice used for keyword search."""
    out = []
    for m in _JS_TEST_CALL_RE.finditer(masked):
        open_idx = m.start(1)
        close_idx = _matching_close_index(text, masked, open_idx, "(", ")")
        if close_idx is None:
            raise ParseFailure("unbalanced parens in an it()/test() call")
        region = text[open_idx : close_idx + 1]
        masked_region = masked[open_idx : close_idx + 1]
        is_async = bool(_JS_ASYNC_CALLBACK_RE.match(region))
        content = _js_content_slice(region, masked_region)
        out.append({"line": _line_no(text, m.start()), "is_async": is_async, "content": content})
    return out


def _annotated_test_regions(text: str, masked: str, annot_re: re.Pattern) -> list[dict]:
    """`{"line", "signature", "body"}` for each method matching `annot_re`
    (a `[Test]`/`@Test`-style attribute/annotation, or a
    `[SetUp]`/`@BeforeEach`-style one when reused by `_mock_reinitialized`)
    — `signature` is the annotation through the parameter list, `body` is
    the brace-balanced method body. Boundaries are found via `masked`
    (Fix 1) so a stray brace/paren inside a body's own string literal can't
    drive the balance past EOF."""
    out = []
    for m in annot_re.finditer(masked):
        paren_idx = masked.find("(", m.end())
        if paren_idx == -1:
            raise ParseFailure("no parameter list found after a test attribute")
        close_paren = _matching_close_index(text, masked, paren_idx, "(", ")")
        if close_paren is None:
            raise ParseFailure("unbalanced parens in an annotated test method's signature")
        brace_idx = masked.find("{", close_paren)
        if brace_idx == -1:
            raise ParseFailure("no method body found after a test attribute")
        close_brace = _matching_close_index(text, masked, brace_idx, "{", "}")
        if close_brace is None:
            raise ParseFailure("unbalanced braces in an annotated test method's body")
        signature = text[m.start() : brace_idx]
        body = text[brace_idx : close_brace + 1]
        out.append({"line": _line_no(text, m.start()), "signature": signature, "body": body})
    return out


def _extract_regions(text: str, masked: str, lang: str) -> list[dict]:
    """Single per-language test-region extraction pass, shared by
    `_check_no_assertion` and `_check_missing_await` (Fix 11)."""
    if lang == "js_ts":
        return _js_ts_test_regions(text, masked)
    if lang == "csharp":
        return _annotated_test_regions(text, masked, _CSHARP_TEST_ATTR_RE)
    if lang == "java":
        return _annotated_test_regions(text, masked, _JAVA_TEST_ANNOT_RE)
    return []


def _python_test_regions(text: str) -> list[tuple[int, str]]:
    """`(line_no, body_text)` for each `def test_*(...)`/`async def
    test_*(...)` — body is every line after the `def` line indented deeper
    than it, up to the first dedent or EOF (blank lines don't count as a
    dedent)."""
    lines = text.split("\n")
    regions = []
    for m in _PY_TEST_DEF_RE.finditer(text):
        indent = m.group(1)
        def_line_idx = text.count("\n", 0, m.start())
        body_lines = []
        for line in lines[def_line_idx + 1 :]:
            if line.strip() == "":
                body_lines.append(line)
                continue
            cur_indent_len = len(line) - len(line.lstrip(" \t"))
            if cur_indent_len <= len(indent):
                break
            body_lines.append(line)
        regions.append((def_line_idx + 1, "\n".join(body_lines)))
    return regions


# --- Per-language signature tables (checks c/d/e) ----------------------------

#: (a) no-assertion and (c) mock-not-reset are file/test-scanned per
#: language; JS/TS/C#/Java cover (a)+(b), Python covers (a) only —
#: test-review.md documents no missing-await/mock-reset/clock-RNG-timer
#: signatures for Python.

_MOCK_CONSTRUCT_MARKERS: dict[str, tuple[re.Pattern, ...]] = {
    "js_ts": (re.compile(r"\bjest\.fn\s*\("), re.compile(r"\bjest\.mock\s*\(")),
    "csharp": (re.compile(r"\bMock<"), re.compile(r"\bSubstitute\.For<")),
    "java": (re.compile(r"\bMockito\.mock\s*\("), re.compile(r"@Mock\b")),
}
_MOCK_RESET_MARKERS: dict[str, re.Pattern] = {
    "js_ts": re.compile(r"\bjest\.clearAllMocks\s*\("),
    "csharp": re.compile(r"\.Reset\s*\(\)|\bClearReceivedCalls\s*\("),
    # Mockito-scoped (Fix 4): the previous bare `\breset\s*\(` matched ANY
    # method literally named `reset(` in the file, including production
    # code under test, which could silently suppress a real finding. This
    # narrower form misses an unqualified `reset()` call reached via
    # `import static org.mockito.Mockito.reset;` — a deliberate, documented
    # trade (see the finding this fixes: an over-broad marker in the wrong
    # direction is worse than a narrow miss here).
    "java": re.compile(r"\bMockito\.reset\s*\("),
}

#: Re-instantiation/re-initialization alternative to an explicit reset call
#: (Fix 4) — test-review.md documents BOTH forms ("Moq `Mock<T>` reused
#: without `Reset()` OR RE-INSTANTIATION"; "Mockito missing `reset()` OR
#: `@BeforeEach` RE-INITIALIZATION"), but `_MOCK_RESET_MARKERS` only ever
#: covered the explicit-call half. `_mock_reinitialized` checks whether a
#: `[SetUp]`/`[TestInitialize]`/`@BeforeEach`/`@BeforeAll` method's own body
#: contains a mock-construct marker — re-creating the mock counts the same
#: as resetting it. JS/TS has no re-instantiation alternative documented in
#: test-review.md (only `jest.clearAllMocks()`), so it has no entry here.

#: REFACTOR (Step 2.2): this table is data-shaped like
#: `internal_double_detector.py`'s `_AMBIENT_API_MARKERS`, but it is NOT the
#: same list and does not share a use case with it, so it is kept separate
#: rather than factored together — see that module's table for the
#: comparison and this file's own module docstring for the one-line
#: pointer. `_AMBIENT_API_MARKERS` answers "does this COLLABORATOR's own
#: declaring file reference ambient state" (evidence for a B2 double
#: waiver: env/hostname/cwd/locale included, no timer/interval markers).
#: This table answers "does this TEST body call an unstubbed clock/RNG/
#: timer API directly" (test-review.md's own non-determinism-sources
#: signatures: no env/hostname/cwd/locale, but adds setTimeout/
#: setInterval/setImmediate/Task.Delay/Thread.Sleep, which
#: `_AMBIENT_API_MARKERS` has no equivalent for). The two tables overlap on
#: three literal substrings (Date/DateTime/Random-family) because both are
#: independently describing "the clock and RNG", not because one was
#: copied from the other — merging them would either strip timer markers
#: this check needs or leak env/hostname markers into a check
#: test-review.md never documented for it.
_CLOCK_RNG_TIMER_MARKERS: dict[str, tuple[re.Pattern, ...]] = {
    "js_ts": (
        re.compile(r"\bDate\.now\s*\("),
        re.compile(r"\bDate\s*\("),
        re.compile(r"\bMath\.random\s*\("),
        re.compile(r"\bsetTimeout\s*\("),
        re.compile(r"\bsetInterval\s*\("),
        re.compile(r"\bsetImmediate\s*\("),
    ),
    "csharp": (
        re.compile(r"\bDateTime\.Now\b"),
        re.compile(r"\bDateTime\.UtcNow\b"),
        re.compile(r"\bDateTimeOffset\.Now\b"),
        re.compile(r"\bnew\s+Random\s*\("),
        re.compile(r"\bTask\.Delay\s*\("),
        re.compile(r"\bThread\.Sleep\s*\("),
    ),
    "java": (
        re.compile(r"\bnew\s+Date\s*\("),
        re.compile(r"\bLocalDateTime\.now\s*\("),
        re.compile(r"\bInstant\.now\s*\("),
        re.compile(r"\bSystem\.currentTimeMillis\s*\("),
        re.compile(r"\bnew\s+Random\s*\("),
        re.compile(r"\bMath\.random\s*\("),
        re.compile(r"\bThread\.sleep\s*\("),
    ),
}

#: Fake-timer/injected-clock markers (Fix 3) — test-review.md's own bullets
#: exempt stubbed usage ("WITHOUT FAKE TIMERS", "WITHOUT INJECTION"), and
#: its Severity Anchors table names `jest.useFakeTimers()` as the remedy.
#: Presence anywhere in the file suppresses the WHOLE
#: unstubbed-clock-rng-timer finding for that file (the same file-level
#: granularity `_MOCK_RESET_MARKERS` already uses for mock-not-reset, not a
#: per-hit check).
_CLOCK_STUB_MARKERS: dict[str, tuple[re.Pattern, ...]] = {
    "js_ts": (
        re.compile(r"\bjest\.useFakeTimers\s*\("),
        re.compile(r"\bvi\.useFakeTimers\s*\("),
        re.compile(r"\bsinon\.useFakeTimers\s*\("),
    ),
    "csharp": (re.compile(r"\bIClock\b"), re.compile(r"\bTimeProvider\b")),
    "java": (re.compile(r"\bClock\.fixed\s*\("),),
}

_REFLECTION_MARKERS: dict[str, tuple[re.Pattern, ...]] = {
    "java": (
        re.compile(r"\bgetDeclaredMethod\b"),
        re.compile(r"\bgetDeclaredField\b"),
        re.compile(r"\.setAccessible\s*\(\s*true\s*\)"),
        re.compile(r"\bMethod\.invoke\b"),
    ),
    "csharp": (
        re.compile(r"\.GetMethod\s*\([^)]*BindingFlags\.NonPublic"),
        re.compile(r"\bInvokeMember\s*\("),
    ),
    "python": (
        re.compile(r"\bgetattr\s*\([^,]+,\s*['\"]_\w+['\"]"),
        re.compile(r"\bsetattr\s*\([^,]+,\s*['\"]_\w+['\"]"),
        re.compile(r"\bhasattr\s*\([^,]+,\s*['\"]_\w+['\"]"),
    ),
    "js_ts": (
        re.compile(r"\[\s*['\"]_\w+['\"]\s*\]"),
        re.compile(r"\bObject\.getOwnPropertyDescriptor\s*\("),
        re.compile(r"\bObject\.defineProperty\s*\("),
    ),
}

#: Tolerated-Deviation Hunt categories, sourced from test-review.md's own
#: grep-pattern prose (language-agnostic — this check has never been
#: per-language in the agent file). NOT "migrated verbatim" (correction —
#: see the module docstring's Tolerated-Deviation Hunt paragraph for the
#: file-scoping disclosure, and below for the qualifier-suppression Fix 8
#: adds on top of the raw grep patterns): each category in test-review.md
#: carries a qualifying clause this table only partially implements —
#: "disabled tests" count only *with no linked issue or expiry*; "aged
#: markers" only *when there is no linked ticket or follow-up action*;
#: "suppressed warnings" only *with no explanatory comment naming the
#: specific approved exception*. For those three categories,
#: `_line_is_qualified` suppresses a hit whose own line or an immediately
#: adjacent line carries a ticket/issue reference or explanatory comment —
#: a cheap same-line-or-adjacent-line approximation, not a real
#: linked-issue lookup. "Relaxed assertions" has no qualifying clause in
#: test-review.md (unconditional). "Widened tolerances" (`changed without
#: a comment explaining the regression`) is inherently diff-based — this
#: single-file scan cannot tell whether a tolerance constant was recently
#: *changed* at all, so that category remains an unqualified upper-bound
#: approximation here; a genuine diff-aware check is out of scope for this
#: fix pass.
_DEVIATION_MARKERS: tuple[tuple[str, re.Pattern], ...] = (
    (
        "disabled-test",
        re.compile(
            r"@Ignore\b|@Disabled\b|\bxit\s*\(|\bxdescribe\s*\(|\btest\.skip\s*\("
            r"|\bit\.skip\s*\(|\[Ignore\]|\[Skip\]|pytest\.mark\.skip\b|pytest\.mark\.xfail\b"
        ),
    ),
    ("aged-marker", re.compile(r"\b(?:TODO|FIXME|HACK|XXX)\b")),
    (
        "suppressed-warning",
        re.compile(
            r"@SuppressWarnings\b|#pragma warning disable|#\s*noqa\b|#\s*type:\s*ignore"
            r"|eslint-disable|pylint:\s*disable"
        ),
    ),
    (
        "relaxed-assertion",
        re.compile(r"either\s+.{0,40}?\s+or\b|\bat least\b|\bapproximately\b|\bdelta\s*=|\bplaces\s*=\s*\d"),
    ),
    ("widened-tolerance", re.compile(r"\b(?:epsilon|tolerance)\s*=")),
)

#: Categories whose test-review.md wording carries a "no linked
#: issue/ticket/exception" qualifier (Fix 8) — checked via
#: `_line_is_qualified`.
_QUALIFIED_DEVIATION_CATEGORIES = frozenset({"disabled-test", "aged-marker", "suppressed-warning"})

#: A ticket/issue reference or explanatory link — `#123`, `PROJ-456`, or a
#: URL/word naming an issue/ticket tracker.
_QUALIFIER_RE = re.compile(r"#\d+|\b[A-Za-z]{2,}-\d+\b|\bissue\b|\bticket\b", re.IGNORECASE)


def _finding(category: str, severity: str | None, line: int, message: str, count: int = 1) -> dict:
    return {"category": category, "severity": severity, "line": line, "message": message, "count": count}


# --- Checks -------------------------------------------------------------------


def _check_no_assertion(regions: list[dict], lang: str) -> list[dict]:
    key = "content" if lang == "js_ts" else "body"
    findings = []
    for entry in regions:
        if not _ASSERTION_RE.search(entry[key]):
            findings.append(
                _finding("no-assertion", "error", entry["line"], "Test has no assertion call — zero regression protection.")
            )
    return findings


def _check_no_assertion_python(text: str) -> list[dict]:
    findings = []
    for line_no, body in _python_test_regions(text):
        if not _ASSERTION_RE.search(body):
            findings.append(
                _finding("no-assertion", "error", line_no, "Test has no assertion call — zero regression protection.")
            )
    return findings


def _check_missing_await(regions: list[dict], lang: str) -> list[dict]:
    findings = []
    if lang == "js_ts":
        for entry in regions:
            if entry["is_async"] and "await" not in entry["content"]:
                findings.append(
                    _finding(
                        "missing-await", "warning", entry["line"], "Async test body has no `await` — likely an unawaited promise."
                    )
                )
    elif lang == "csharp":
        for entry in regions:
            if _CSHARP_ASYNC_TASK_RE.search(entry["signature"]) and "await" not in entry["body"]:
                findings.append(
                    _finding(
                        "missing-await",
                        "warning",
                        entry["line"],
                        "`async Task` test method has no `await` — likely an unresolved Task.",
                    )
                )
    elif lang == "java":
        for entry in regions:
            if _JAVA_FUTURE_TYPE_RE.search(entry["body"]) and not _JAVA_FUTURE_RESOLVED_RE.search(entry["body"]):
                findings.append(
                    _finding(
                        "missing-await",
                        "warning",
                        entry["line"],
                        "Test body references Future/CompletableFuture with no `.get()`/`.join()` resolution.",
                    )
                )
    return findings


def _mock_reinitialized(text: str, masked: str, lang: str) -> bool:
    """True when a `[SetUp]`/`[TestInitialize]`/`@BeforeEach`/`@BeforeAll`
    method's own body contains a mock-construct marker (Fix 4) — the
    re-instantiation/re-initialization alternative test-review.md
    documents alongside an explicit reset call."""
    setup_re = _SETUP_ANNOT_RE.get(lang)
    construct_markers = _MOCK_CONSTRUCT_MARKERS.get(lang)
    if not setup_re or not construct_markers:
        return False
    for entry in _annotated_test_regions(text, masked, setup_re):
        if any(marker.search(entry["body"]) for marker in construct_markers):
            return True
    return False


def _check_mock_not_reset(text: str, masked: str, lang: str) -> list[dict]:
    construct_markers = _MOCK_CONSTRUCT_MARKERS.get(lang)
    if not construct_markers:
        return []
    hit_lines = [_line_no(text, m.start()) for marker in construct_markers for m in marker.finditer(text)]
    if not hit_lines:
        return []
    reset_marker = _MOCK_RESET_MARKERS[lang]
    if reset_marker.search(text):
        return []
    if _mock_reinitialized(text, masked, lang):
        return []
    return [
        _finding(
            "mock-not-reset",
            "warning",
            min(hit_lines),
            f"{len(hit_lines)} mock/stub construction site(s) with no reset/clear call found in this file.",
            count=len(hit_lines),
        )
    ]


def _check_unstubbed_clock_rng_timer(text: str, lang: str) -> list[dict]:
    if any(marker.search(text) for marker in _CLOCK_STUB_MARKERS.get(lang, ())):
        return []
    findings = []
    for marker in _CLOCK_RNG_TIMER_MARKERS.get(lang, ()):
        for m in marker.finditer(text):
            findings.append(
                _finding(
                    "unstubbed-clock-rng-timer",
                    "warning",
                    _line_no(text, m.start()),
                    f"Unstubbed clock/RNG/timer access: {m.group(0)!r}.",
                )
            )
    return findings


def _check_reflection_primary_strategy(text: str, lang: str) -> list[dict]:
    findings = []
    for marker in _REFLECTION_MARKERS.get(lang, ()):
        for m in marker.finditer(text):
            findings.append(
                _finding(
                    "reflection-primary-strategy",
                    "warning",
                    _line_no(text, m.start()),
                    f"Reflection into private members: {m.group(0)!r}. Architecture/encapsulation issue, not a test-hygiene nit.",
                )
            )
    return findings


def _line_is_qualified(lines: list[str], line_no: int) -> bool:
    """True when the marker's own line, or the immediately preceding/
    following line, carries a ticket/issue reference or explanatory
    comment (Fix 8)."""
    for idx in (line_no - 2, line_no - 1, line_no):
        if 0 <= idx < len(lines) and _QUALIFIER_RE.search(lines[idx]):
            return True
    return False


def _check_tolerated_deviation(text: str) -> list[dict]:
    lines = text.split("\n")
    hits = []
    for name, marker in _DEVIATION_MARKERS:
        for m in marker.finditer(text):
            line_no = _line_no(text, m.start())
            if name in _QUALIFIED_DEVIATION_CATEGORIES and _line_is_qualified(lines, line_no):
                continue
            hits.append((name, line_no))
    if len(hits) < CONSOLIDATION_THRESHOLD:
        return []
    hits.sort(key=lambda h: h[1])
    listing = ", ".join(f"{name}@L{line}" for name, line in hits)
    return [
        _finding(
            "tolerated-deviation-consolidation",
            "warning",
            hits[0][1],
            f"Fail-safe posture erosion: {len(hits)} tolerated-deviation artifacts co-located in this file ({listing}).",
            count=len(hits),
        )
    ]


def _is_under_test_dir(root: Path, file_path: Path) -> bool:
    try:
        rel = file_path.resolve().relative_to(root.resolve())
    except ValueError:
        rel = file_path
    return any(part.lower() in _TEST_DIR_NAMES for part in rel.parts)


def _translate_double_detector_findings(
    root: Path,
    file_path: Path,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> tuple[list[dict], bool]:
    """Run `internal_double_detector.py --files <file> --json` (via the
    injectable `runner`, defaulting to the real `subprocess.run` — Fix 13)
    and translate each `verdict == "high"` finding into this script's own
    `error`-severity `internal-collaborator-doubling` finding. The reused
    script's raw JSON is never checked for a `severity` field — it doesn't
    have one.

    Returns `(findings, doubling_check_ran)`. `doubling_check_ran` is
    `False` when the file's path has no `test`/`tests` segment (the
    detector's own `analyze()` never scans it — Fix 6's out-of-scope
    disclosure) or when the subprocess call/JSON parse fails (Fix 5); it
    is `True` only when the detector actually ran and reported."""
    if not _is_under_test_dir(root, file_path):
        return (
            [
                _finding(
                    "internal-collaborator-doubling-out-of-scope",
                    "warning",
                    _UNKNOWN_LINE,
                    "internal_double_detector.py only scans files under a "
                    "'test'/'tests' path segment; this file's path has no "
                    "such segment, so the doubling check did not run for it "
                    "— even though this repo's own test-file conventions "
                    "(*.test.*, *.spec.*, __tests__/) would still recognize "
                    "it as a test file. mechanicalFail is unaffected by the "
                    "doubling category specifically for this file.",
                )
            ],
            False,
        )
    try:
        completed = runner(
            [sys.executable, str(_DETECTOR_PATH), str(root), "--files", str(file_path), "--json"],
            capture_output=True,
            text=True,
            timeout=_DOUBLE_DETECTOR_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return (
            [
                _finding(
                    "internal-collaborator-doubling-unavailable",
                    "warning",
                    _UNKNOWN_LINE,
                    f"internal_double_detector.py could not be run: {exc}",
                )
            ],
            False,
        )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return (
            [
                _finding(
                    "internal-collaborator-doubling-unavailable",
                    "warning",
                    _UNKNOWN_LINE,
                    "internal_double_detector.py did not emit valid JSON: "
                    f"exit={completed.returncode} stderr={completed.stderr.strip()!r}",
                )
            ],
            False,
        )
    findings = []
    for entry in payload.get("findings", []):
        if entry.get("verdict") == "high":
            findings.append(
                _finding(
                    "internal-collaborator-doubling",
                    "error",
                    entry.get("line", _UNKNOWN_LINE),
                    entry.get("message", "internal_double_detector.py reported a high-verdict finding."),
                )
            )
    return findings, True


_GATING_CATEGORIES = frozenset({"no-assertion", "internal-collaborator-doubling"})


def analyze_file(
    root: Path,
    file_path: Path,
    double_detector_runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> dict:
    """Compute the mechanical pre-phase result for `file_path` (scanned
    against `root` for `internal_double_detector.py`'s first-party index).
    `double_detector_runner` is injectable (Fix 13) — defaults to the real
    `subprocess.run`; tests exercising unrelated checks can pass a stub to
    avoid the real subprocess-spawn cost.

    Returns `{"file", "mechanicalFail", "findings", "skippedQualitative",
    "doublingCheckRan"}`. Never raises — a decode/parse failure becomes a
    `parse-failure` finding with `mechanicalFail: False` (the file falls
    through to the qualitative pass rather than being dropped)."""
    lang = LANG_BY_EXT.get(file_path.suffix)

    try:
        text = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return {
            "file": str(file_path),
            "mechanicalFail": False,
            "findings": [_finding("parse-failure", None, _UNKNOWN_LINE, f"Could not read/decode file: {exc}")],
            "skippedQualitative": False,
            "doublingCheckRan": False,
        }

    findings: list[dict] = []
    try:
        masked = _mask_code(text)
        regions = _extract_regions(text, masked, lang) if lang else []
        if lang == "python":
            findings += _check_no_assertion_python(text)
        elif lang in ("js_ts", "csharp", "java"):
            findings += _check_no_assertion(regions, lang)
            findings += _check_missing_await(regions, lang)
        if lang:
            findings += _check_mock_not_reset(text, masked, lang)
            findings += _check_unstubbed_clock_rng_timer(text, lang)
            findings += _check_reflection_primary_strategy(text, lang)
        findings += _check_tolerated_deviation(text)
    except ParseFailure as exc:
        return {
            "file": str(file_path),
            "mechanicalFail": False,
            "findings": [_finding("parse-failure", None, _UNKNOWN_LINE, str(exc))],
            "skippedQualitative": False,
            "doublingCheckRan": False,
        }

    doubling_findings, doubling_check_ran = _translate_double_detector_findings(root, file_path, double_detector_runner)
    findings += doubling_findings

    mechanical_fail = any(f["category"] in _GATING_CATEGORIES and f["severity"] == "error" for f in findings)
    return {
        "file": str(file_path),
        "mechanicalFail": mechanical_fail,
        "findings": findings,
        "skippedQualitative": mechanical_fail,
        "doublingCheckRan": doubling_check_ran,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", help="Project root (passed through to internal_double_detector.py)")
    parser.add_argument("file", help="Test file to analyze (absolute, or relative to root)")
    args = parser.parse_args(argv)

    root = Path(args.root)
    file_path = Path(args.file)
    if not file_path.is_absolute():
        file_path = root / file_path

    print(json.dumps(analyze_file(root, file_path)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
