"""Shared `scripts/ci-local.sh` source parsers for the floor/ceiling gate
tests — a bash-invocation parser (`pytest_invocation()`/`lines_after_invocation()`)
and a registry-array parser (`check_registry()`).

`tests/repo/test_python_floor.py` (`chk_python_floor`) and
`tests/repo/test_python_ceiling.py` (`chk_python_ceiling`) each need to find
a shell function's `-m pytest` invocation, walk its backslash
line-continuations the way bash itself does, and split it into
`(prefix, pytest's own arguments, tokens after a "||" tail)` — the shape
each gate's tests pin against, since any of those three pieces silently
narrowing what actually runs is exactly the failure mode both gates exist to
catch. The two test files independently grew near-line-for-line-identical
parsers for this (`_floor_invocation` / `_floor_check_body` /
`_without_comments` vs. `_ceiling_invocation` / `_ceiling_check_body` /
`_without_comments`), and a fix to one — the comment-stripping-before-
continuation-walk bug caught during #1876/#1885's review — had to be
ported to the other by hand rather than being inherited automatically.
Flagged independently by structure-review, test-review, test-smell-review,
and arch-review during that PR's review (#1887); arch-review additionally
found the two files' `CHECKS=(`/`OPTIONAL_CHECKS=(` registry-array parsing
(`check_registry` below) was a second, still-live instance of the same
duplication class.

Scoped to the repo root via the `pythonpath = .` entry in `pytest.ini`,
matching `_content_guard_scan.py`'s own convention (the closest precedent: a
helper shared by exactly two `tests/repo/` files) — a `tests/repo/`-local
sibling would also work with its own `pythonpath` entry, but the repo-root
entry already exists and needs no addition.
"""

from __future__ import annotations

from typing import NamedTuple


class PytestInvocation(NamedTuple):
    """`pytest_invocation()`'s successful-parse result (`None` is the
    unparseable sentinel — see that function). Tuple-compatible (plain-tuple
    equality and `prefix, args, tail = ...` both still work) so this is
    purely additive over the plain-tuple shape both consumers already
    pinned."""

    prefix: list[str]
    args: list[str]
    tail: list[str]


def check_body(ci_local: str, fn_name: str) -> str:
    """The text of the bash function `fn_name`'s body.

    Bounded from the function's header to the next top-level `chk_`-prefixed
    function definition — every check in `scripts/ci-local.sh` follows that
    naming convention, so this window reliably stops at the next one without
    needing to parse bash scoping. If `fn_name` is not actually defined in
    `ci_local`, the header split is a no-op but the second split still runs —
    so the result is everything up to the first `chk_`-prefixed function
    ANYWHERE in `ci_local`, not the whole input unchanged. For the real
    `scripts/ci-local.sh` (preamble, then `chk_` functions in sequence) that
    happens to equal the preamble; it is not guaranteed for arbitrary text.
    Every current caller pins `fn_name`'s existence separately, so this
    stays a plain split rather than raising."""
    return ci_local.split(f"{fn_name}()", 1)[-1].split("\nchk_", 1)[0]


def check_registry(ci_local: str, array_name: str) -> str:
    """The text of a bash array declaration named `array_name` (e.g.
    `CHECKS` or `OPTIONAL_CHECKS`), from the line that starts with
    `<array_name>=(` to the line that starts with `)`.

    The opening delimiter is anchored to a line start (`\\n{array_name}=(`,
    with `ci_local` conceptually prefixed by a newline so a declaration at
    byte 0 still matches): an unanchored substring match would let `CHECKS`
    match inside `OPTIONAL_CHECKS=(` too, since one name is a substring of
    the other, and only today's declaration order in `scripts/ci-local.sh`
    would keep that accidentally correct. The closing delimiter is anchored
    the same way for the same reason the module docstring's history already
    explains: check labels contain literal parens (like `"(run-all.sh)"`),
    so an unanchored `)` split truncates the array at the first check whose
    label happens to include one.

    Raises `ValueError` if `array_name` is not declared at a line start at
    all, or if its declaration is never followed by a line starting with
    `)` — both guard the same "x" not in registry vacuous-pass shape a
    silent wrong-window fallback would otherwise produce, at each end of
    the span. Unlike `check_body`, no current caller of this function
    separately confirms the array's existence."""
    marker = f"\n{array_name}=("
    haystack = "\n" + ci_local
    if marker not in haystack:
        raise ValueError(f"{array_name}=( is not declared at the start of a line")
    remainder = haystack.split(marker, 1)[-1]
    if "\n)" not in remainder:
        raise ValueError(f"{array_name}=( is never closed by a line starting with )")
    return remainder.split("\n)", 1)[0]


def synthetic_check(fn_name: str, body: str) -> str:
    """A minimal `ci-local.sh` fragment shaped so `check_body(text, fn_name)`
    finds its window — a bash function named `fn_name` wrapping `body`,
    followed by a sentinel next function so the window has a real end."""
    return f"{fn_name}() {{\n{body}\n}}\n\nchk_next() {{ :; }}\n"


def without_comments(text: str) -> str:
    """`text` with whole-line comments removed.

    Whole-line only — an inline trailing comment on a real code line still
    counts, so a suppressor cannot hide a narrowing flag behind one. Note
    `pytest_invocation()` and `lines_after_invocation()` deliberately do NOT run
    their own continuation-walk through this function first: inside a
    continued command a `#` line truncates the command rather than
    commenting itself out, so there its tokens must survive."""
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )


def _marker_span(lines: list[str]) -> tuple[int, int] | None:
    """The `(start, end)` line-index span, within `lines`, of the continued
    command containing the sole `-m pytest` marker — walked outward while
    lines continue, the way bash reads a backslash-continued command.

    Continuation is tested on the RAW line: bash reads a `\\` followed by a
    space as an escaped space that ENDS the command, so a trailing space
    after a backslash must end the span here too, or a command the shell had
    truncated would be read as spanning further than it really does.

    `-m pytest` must appear on exactly one non-comment LINE for a span to be
    returned at all — a same-line duplicate (two markers, or a decoy on the
    same line as the real call) is not itself rejected here; it is caught
    downstream instead, by the callers' own prefix/argument equality pins
    against whichever marker `pytest_invocation()` anchors on. Returns `None` when
    no line qualifies or more than one does, which both callers below turn
    into a loud failure rather than a guessed one.
    """
    marks = [
        i
        for i, line in enumerate(lines)
        if "-m pytest" in line and not line.lstrip().startswith("#")
    ]
    if len(marks) != 1:
        return None
    start = end = marks[0]
    while start > 0 and lines[start - 1].endswith("\\"):
        start -= 1
    while end < len(lines) - 1 and lines[end].endswith("\\"):
        end += 1
    return start, end


def _tokenize_span(lines: list[str]) -> tuple[list[str], list[str]]:
    """Every whitespace-separated token in `lines` (a continuation span),
    split into `(tokens before any "||", tokens after it)`.

    Pulled out of `pytest_invocation()` so that function's own loop nesting stays
    shallow — this is the one place a `\\`-continuation line is stripped of
    its trailing backslash and split, and the one place a `"||"` token
    switches the accumulator from `tokens` to `tail` rather than being kept
    itself."""
    tokens: list[str] = []
    tail: list[str] = []
    seen_or = False
    for line in lines:
        for token in line.removesuffix("\\").split():
            if token == "||":
                seen_or = True
                continue
            (tail if seen_or else tokens).append(token)
    return tokens, tail


def pytest_invocation(ci_local: str, fn_name: str) -> PytestInvocation | None:
    """`fn_name`'s pytest command, split at `-m pytest` and at any `||`.

    Returns `(tokens before the marker, pytest's own arguments, tokens after
    a "||" on the same continued command)`. All three matter independently:
    the prefix decides which interpreter runs and which ambient environment
    survives, the arguments decide what pytest actually collects and runs,
    and a non-empty tail means the invocation's exit status is no longer
    pytest's own.

    Tokenizing is whitespace-based, so a behaviour-preserving reflow of the
    continuation does not fail a caller's pin whose subject never changed.

    Comments are deliberately NOT stripped before walking the continuation
    or tokenizing (only `_marker_span`'s own marker SCAN excludes them, so a
    comment merely mentioning `-m pytest` cannot supply a decoy match): a
    `#` line carrying a trailing backslash does not comment itself out of a
    continued command, it truncates the command there, so pytest would
    receive only the arguments above it. Stripping that comment line first
    would silently splice the surrounding continuation lines back together
    and report a full argument list for an invocation the real shell had cut
    short — the exact outcome every gate this module backs must never
    produce. The comment's own tokens flow into `tokens`/`tail` like any
    other token, where a caller's own allowlist or equality check against
    them is what actually rejects them.

    Tokens after `||` are returned separately rather than dropped, so a
    failure path that discards or replaces the verdict (`-q || printf
    'failed'`) is visible to the caller instead of silently passing through
    as an unconditional run.

    Returns `None` when the marker is missing, ambiguous, or not immediately
    followed by `pytest` — an unambiguous sentinel, distinct in principle
    from a legitimate empty parse (mirrors `lines_after_invocation()`'s own
    unparseable sentinel, a string no real code line can produce). A command
    truncated exactly at `-m pytest`, with no trailing arguments at all, is
    NOT specially rejected either — it returns `(prefix, [], tail)` rather
    than `None`, relying on a caller's own argument-equality pin (never a
    denylist) to still fail on the empty `args`.
    """
    lines = check_body(ci_local, fn_name).splitlines()
    span = _marker_span(lines)
    if span is None:
        return None
    start, end = span
    tokens, tail = _tokenize_span(lines[start : end + 1])
    if "-m" not in tokens:
        return None
    marker = tokens.index("-m")
    if tokens[marker + 1 : marker + 2] != ["pytest"]:
        return None
    return PytestInvocation(tokens[:marker], tokens[marker + 2 :], tail)


def lines_after_invocation(ci_local: str, fn_name: str) -> list[str]:
    """Real code lines in `fn_name`'s body strictly after the (possibly
    multi-line) pytest invocation ends.

    A bash function returns its LAST command's status, and `ci-local.sh`
    runs without `set -e`, so any statement appended after the invocation —
    a stray `printf`, a `true`, an unconditional `return 0` — silently
    becomes the gate's verdict instead of pytest's own exit code. The
    function's closing `}` is not a statement, and a trailing comment has no
    bearing on what bash actually executes, so both are excluded from the
    result — unlike `pytest_invocation()`'s own continuation span, where excluding
    a comment could hide a narrowing bypass; here it can only stop this
    rule's own documentation from tripping the check.

    Returns a one-element sentinel list when the marker is missing or
    ambiguous (mirroring `pytest_invocation()`'s own `None` sentinel), since
    there is no invocation boundary to measure "after" from."""
    lines = check_body(ci_local, fn_name).splitlines()
    span = _marker_span(lines)
    if span is None:
        return ["<unparseable: -m pytest marker not found exactly once>"]
    _, end = span
    return [
        stripped
        for line in lines[end + 1 :]
        if (stripped := line.strip())
        and stripped != "}"
        and not stripped.startswith("#")
    ]
