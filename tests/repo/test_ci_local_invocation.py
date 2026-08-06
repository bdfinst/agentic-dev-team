"""Direct tests of the shared `_ci_local_invocation` parser (#1887).

`test_python_floor.py` and `test_python_ceiling.py` both pin this parser
against their own gate's synthetic bodies — `TestTheSliceParserItself` and
`TestTheCeilingParserItself` respectively — but neither pins the parser's
OWN contract under a neutral name. Flagged independently by test-smell-review,
test-review, domain-review, and arch-review during #1887's own review: the
production-code duplication the module was extracted to remove had, without
this file, simply moved one layer up into the two consumers' near-identical
parser-edge-case tests. This file is additive, not a replacement — it does
not remove or narrow either consumer's existing test classes, which the
extraction requires to keep passing byte-for-byte on their pre-existing
assertions; it only gives the shared module a test surface of its own, using
a neutral synthetic function name (`chk_neutral`) rather than either gate's.

`without_comments()` is deliberately NOT re-tested here: it already has
exactly one canonical test, in `test_python_floor.py`'s
`test_without_comments_strips_whole_lines_but_keeps_inline_ones`, whose own
docstring notes it is shared with `test_python_ceiling.py` via this module —
duplicating it a third time here would be the same test-effort duplication
this file exists to stop adding to.
"""

from __future__ import annotations

import pytest

from _ci_local_invocation import (
    PytestInvocation,
    check_body,
    check_registry,
    lines_after_invocation,
    pytest_invocation,
    synthetic_check,
)

#: A name belonging to neither real gate, so a passing test here can never be
#: mistaken for coverage of gate-specific behavior (that stays in each
#: consumer's own test class).
NEUTRAL_FN = "chk_neutral"


def test_check_body_finds_the_named_function():
    text = synthetic_check(NEUTRAL_FN, "  echo hi")
    assert check_body(text, NEUTRAL_FN) == " {\n  echo hi\n}\n"


def test_check_body_stops_before_the_next_chk_function():
    text = "chk_a() {\n  first\n}\nchk_b() {\n  second\n}\n"
    assert "second" not in check_body(text, "chk_a")


def test_check_body_with_an_unknown_function_name_stops_at_the_first_chk_anyway():
    """The documented fallback (test-review, #1887): with `fn_name` absent,
    the FIRST split is a no-op (no separator found, so it returns the whole
    input), but the SECOND split still runs — truncating at the first
    `"\\nchk_"` anywhere in that unchanged input, not just after `fn_name`'s
    own header. So this does NOT reliably return the whole input unchanged;
    it returns everything up to the first OTHER `chk_`-prefixed function,
    which for the real `scripts/ci-local.sh` (preamble, then chk_ functions
    in sequence) happens to equal the preamble, but is not guaranteed for
    arbitrary text where the first function is itself `chk_`-prefixed and
    isn't `fn_name` — exactly this synthetic case. Every current caller
    separately pins `f"{fn_name}()" in ci_local` before trusting this
    function's result, so this fallback shape is pinned here directly
    rather than only by inference."""
    text = synthetic_check(NEUTRAL_FN, "  echo hi")
    assert check_body(text, "chk_missing") == "chk_neutral() {\n  echo hi\n}\n"


def test_check_registry_splits_at_the_closing_paren_line():
    text = 'CHECKS=(\n  "chk_a (label)"\n  "chk_b"\n)\nOPTIONAL_CHECKS=(\n  "chk_c"\n)\n'
    assert check_registry(text, "CHECKS") == '\n  "chk_a (label)"\n  "chk_b"'
    assert check_registry(text, "OPTIONAL_CHECKS") == '\n  "chk_c"'


def test_check_registry_is_anchored_against_the_name_collision():
    """`CHECKS` is a substring of `OPTIONAL_CHECKS`, so an unanchored match
    would let `check_registry(text, "CHECKS")` land inside
    `OPTIONAL_CHECKS=(` too. Declared first here (reversed from the test
    above and from `scripts/ci-local.sh`'s own order) specifically so this
    case cannot pass by declaration-order coincidence the way the
    unanchored version once did (domain-review, correctness-review,
    arch-review — all three independently, #1887)."""
    text = 'OPTIONAL_CHECKS=(\n  "chk_c"\n)\nCHECKS=(\n  "chk_a"\n)\n'
    assert check_registry(text, "CHECKS") == '\n  "chk_a"'
    assert check_registry(text, "OPTIONAL_CHECKS") == '\n  "chk_c"'


def test_check_registry_raises_when_the_array_name_is_absent():
    """Unlike `check_body`'s documented (if imprecise) fallback,
    `check_registry` raises rather than silently returning a wrong window —
    added after security-review and domain-review both independently found
    that a silent fallback here let a negative membership assertion
    (`"x" not in registry`) pass vacuously against text that was not the
    named array at all (#1887)."""
    text = 'CHECKS=(\n  "chk_a"\n)\n'
    with pytest.raises(ValueError):
        check_registry(text, "OPTIONAL_CHECKS")


def test_check_registry_raises_when_the_declaration_is_never_closed():
    """The closing delimiter needs the same guard as the opening one
    (domain-review, second closing pass, #1887): an unclosed array — no
    line starting with `)` anywhere after the declaration — would
    otherwise silently return an over-wide window (everything to EOF, or
    to the next line-start `)` belonging to a DIFFERENT array), the exact
    vacuous-pass shape the opening-delimiter guard was added to prevent,
    just at the other end of the span."""
    text = 'CHECKS=(\n  "chk_a"\n'
    with pytest.raises(ValueError):
        check_registry(text, "CHECKS")


def test_check_registry_raises_for_an_indented_declaration():
    """A declaration that IS present but not anchored at a line start (an
    indented reassignment, a `declare`/`readonly` prefix) is not the
    line-start form this function's anchor requires — it should raise
    the same as a genuinely absent array, not silently match a DIFFERENT,
    unrelated `)`-terminated block below it (domain-review, #1887)."""
    text = '  CHECKS=(\n  "chk_a"\n)\n'
    with pytest.raises(ValueError):
        check_registry(text, "CHECKS")


def test_invocation_reads_prefix_args_and_tail():
    body = synthetic_check(
        NEUTRAL_FN,
        "  FOO= uv run -m pytest \\\n    tests/a \\\n    -q || return 1",
    )
    result = pytest_invocation(body, NEUTRAL_FN)
    assert result == PytestInvocation(["FOO=", "uv", "run"], ["tests/a", "-q"], ["return", "1"])
    # PytestInvocation is tuple-compatible: unpacking and plain-tuple equality
    # both still work, which is the whole point of it being a NamedTuple —
    # but named-field access is the one thing a plain tuple couldn't do, so
    # that needs its own assertion rather than riding along on the others.
    prefix, args, tail = result
    assert (prefix, args, tail) == (["FOO=", "uv", "run"], ["tests/a", "-q"], ["return", "1"])
    assert result.prefix == ["FOO=", "uv", "run"]
    assert result.args == ["tests/a", "-q"]
    assert result.tail == ["return", "1"]


def test_invocation_is_unparseable_without_a_single_marker():
    assert pytest_invocation(synthetic_check(NEUTRAL_FN, "  echo hi"), NEUTRAL_FN) is None
    two_markers = "  uv run -m pytest a -q\n  uv run -m pytest b -q"
    assert (
        pytest_invocation(synthetic_check(NEUTRAL_FN, two_markers), NEUTRAL_FN) is None
    )


def test_invocation_does_not_specially_reject_zero_trailing_args():
    """A command truncated exactly at `-m pytest` is not treated as
    unparseable — it returns empty `args` rather than `None`, documented as
    a deliberate choice in `pytest_invocation()`'s own docstring
    (correctness-review, #1887)."""
    body = synthetic_check(NEUTRAL_FN, "  uv run -m pytest")
    assert pytest_invocation(body, NEUTRAL_FN) == (["uv", "run"], [], [])


def test_lines_after_invocation_finds_a_trailing_statement():
    body = synthetic_check(NEUTRAL_FN, "  uv run -m pytest tests/a -q\n  echo done")
    assert lines_after_invocation(body, NEUTRAL_FN) == ["echo done"]


def test_lines_after_invocation_is_empty_for_the_clean_case():
    body = synthetic_check(NEUTRAL_FN, "  uv run -m pytest tests/a -q")
    assert lines_after_invocation(body, NEUTRAL_FN) == []


def test_lines_after_invocation_returns_the_sentinel_when_unparseable():
    """The one branch neither consumer's synthetic-body tests exercised
    (test-review, #1887): a missing/ambiguous marker means there is no
    invocation boundary to measure "after" from at all. Covers both ways
    `_marker_span` returns `None` — missing entirely, and ambiguous (two
    markers) — since they are logically distinct per its own docstring,
    even though both currently produce the identical sentinel here."""
    sentinel = ["<unparseable: -m pytest marker not found exactly once>"]
    missing = synthetic_check(NEUTRAL_FN, "  echo hi")
    assert lines_after_invocation(missing, NEUTRAL_FN) == sentinel
    two_markers = synthetic_check(
        NEUTRAL_FN, "  uv run -m pytest a -q\n  uv run -m pytest b -q"
    )
    assert lines_after_invocation(two_markers, NEUTRAL_FN) == sentinel


# ---------------------------------------------------------------------------
# #1895 item 3: the shared parser edge-case table
# ---------------------------------------------------------------------------
#
# `TestTheSliceParserItself` (test_python_floor.py) and
# `TestTheCeilingParserItself` (test_python_ceiling.py) each re-test these
# same boundary rules — marker ambiguity, continuation-reflow invariance,
# truncating-comment survival, backslash-trailing-space termination, and the
# `||` tail being returned rather than dropped — nearly identically, just
# against their own gate-specific paths/dirs (slice test-file paths for the
# floor, `tests/repo`-style directories for the ceiling).
#
# This table is declared here, against the neutral `NEUTRAL_FN` and generic
# `tests/a`/`tests/b` tokens, so it tests `pytest_invocation()`'s own
# contract rather than either gate's domain-specific argument shape.
# Deliberately NOT force-migrated into either frozen class in this pass:
# both must keep passing byte-for-byte on their EXISTING assertions (the
# hard constraint the original extraction, #1887, imposed), and pointing
# them at this table instead is a separate, higher-risk change a later pass
# could make without editing those assertions at all — this table would
# already be here, ready to adopt.
SHARED_PARSER_EDGE_CASES = (
    pytest.param(
        (
            '  uv run --python "$py" \\\n'
            "    -m pytest \\\n"
            "    tests/a \\\n"
            "    tests/b \\\n"
            "    -q"
        ),
        PytestInvocation(["uv", "run", "--python", '"$py"'], ["tests/a", "tests/b", "-q"], []),
        id="continuation-reflow-is-invariant",
    ),
    pytest.param(
        '  uv run --python "$py" -m pytest tests/a tests/b -q',
        PytestInvocation(["uv", "run", "--python", '"$py"'], ["tests/a", "tests/b", "-q"], []),
        id="one-line-form-matches-the-continued-form",
    ),
    pytest.param(
        "  printf 'about to run -m pytest\\n'\n  uv run -m pytest tests/a -q",
        None,
        id="a-second-marker-is-ambiguous",
    ),
    pytest.param(
        "  uv run tests/a",
        None,
        id="a-missing-marker-is-unparseable",
    ),
    pytest.param(
        (
            "  uv run -m pytest \\\n"
            "    tests/a \\\n"
            "    # note \\\n"
            "    tests/b \\\n"
            "    -q"
        ),
        PytestInvocation(["uv", "run"], ["tests/a", "#", "note", "tests/b", "-q"], []),
        id="a-truncating-comment-survives-into-args",
    ),
    pytest.param(
        (
            "  uv run -m pytest \\\n"
            "    tests/a \\ \n"
            "    tests/b \\\n"
            "    -q"
        ),
        PytestInvocation(["uv", "run"], ["tests/a", "\\"], []),
        id="a-backslash-with-a-trailing-space-ends-the-command",
    ),
    pytest.param(
        "  uv run -m pytest tests/a -q || printf 'failed'",
        PytestInvocation(["uv", "run"], ["tests/a", "-q"], ["printf", "'failed'"]),
        id="the-failure-tail-is-returned-not-discarded",
    ),
)


@pytest.mark.parametrize("body_text,expected", SHARED_PARSER_EDGE_CASES)
def test_shared_parser_edge_case_table(body_text: str, expected) -> None:
    """The consolidated table above, run against the neutral `NEUTRAL_FN`."""
    body = synthetic_check(NEUTRAL_FN, body_text)
    assert pytest_invocation(body, NEUTRAL_FN) == expected
