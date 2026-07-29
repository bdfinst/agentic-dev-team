"""Unit tests for scripts/lib/_gherkin_text.py (issue #1526).

Exercises `safe_for_terminal` and `is_tag_line` directly against the shared
helper — hoisted here from `gherkin_failure_path_gate.py` and
`gherkin_cross_feature_duplicate_titles_gate.py`'s duplicate copies (each
script's own test file covers its own behavior built on top of this shared
helper, not this module's internals a second time).
"""

from __future__ import annotations

import sys

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "scripts" / "lib"))

import _gherkin_text as gherkin_text


def test_safe_for_terminal_strips_c0_control_characters():
    assert gherkin_text.safe_for_terminal("returns error\x1b[31m") == "returns error[31m"


def test_safe_for_terminal_strips_c1_control_characters():
    assert gherkin_text.safe_for_terminal("returns error\x9btitle") == "returns errortitle"


def test_safe_for_terminal_bounds_length_to_default_limit():
    result = gherkin_text.safe_for_terminal("x" * 300)
    assert len(result) == gherkin_text.TERMINAL_DISPLAY_LIMIT


def test_safe_for_terminal_respects_explicit_limit():
    assert gherkin_text.safe_for_terminal("abcdef", limit=3) == "abc"


def test_safe_for_terminal_passes_through_ordinary_text_unchanged():
    assert gherkin_text.safe_for_terminal("returns 201 Created") == "returns 201 Created"


def test_safe_for_terminal_strips_embedded_newlines():
    """This helper is also applied to filesystem paths (issue #1526), which
    have no line-oriented `.strip()` guarantee the way a parsed title does —
    an embedded CR/LF must not survive, or a crafted path could forge a fake
    extra report line."""
    assert gherkin_text.safe_for_terminal("orders\nOK: fake line") == "ordersOK: fake line"
    assert gherkin_text.safe_for_terminal("orders\r\nOK: fake line") == "ordersOK: fake line"


def test_safe_for_terminal_strips_tabs():
    assert gherkin_text.safe_for_terminal("orders\ttab") == "orderstab"


def test_safe_for_terminal_strips_unicode_line_and_paragraph_separators():
    """Issue #1529: some terminals render U+2028/U+2029 as a hard line
    break even though they're outside the ASCII C0/C1 range the CR/LF fix
    (issue #1526) covered — the same fake-report-line-forgery risk, in a
    non-ASCII variant."""
    assert gherkin_text.safe_for_terminal("orders\u2028OK: fake line") == "ordersOK: fake line"
    assert gherkin_text.safe_for_terminal("orders\u2029OK: fake line") == "ordersOK: fake line"


def test_safe_for_terminal_strips_unicode_bidi_override_characters():
    """Issue #1529: a bidirectional-override character (e.g. U+202E
    RIGHT-TO-LEFT OVERRIDE) can visually spoof a printed path/title
    (Trojan-Source-style) by reordering how the surrounding text renders."""
    assert gherkin_text.safe_for_terminal("orders\u202etitle") == "orderstitle"
    assert gherkin_text.safe_for_terminal("orders\u202atitle") == "orderstitle"


def test_safe_for_terminal_strips_unicode_bidi_isolate_characters():
    assert gherkin_text.safe_for_terminal("orders\u2066iso\u2069") == "ordersiso"



def test_is_tag_line_true_for_single_tag():
    assert gherkin_text.is_tag_line("  @error-handling\n") is True


def test_is_tag_line_true_for_multiple_tags():
    assert gherkin_text.is_tag_line("@wip @error-handling\n") is True


def test_is_tag_line_false_for_blank_line():
    assert gherkin_text.is_tag_line("\n") is False


def test_is_tag_line_false_for_scenario_line():
    assert gherkin_text.is_tag_line("  Scenario: returns 400\n") is False


def test_is_tag_line_false_when_only_some_tokens_are_tagged():
    assert gherkin_text.is_tag_line("@wip not-a-tag\n") is False


def _lines(text):
    return text.splitlines(keepends=True)


def test_trim_trailing_tag_run_backs_up_over_a_trailing_tag_and_blank_line():
    lines = _lines(
        "Feature: POST /orders\n"
        "\n"
        "  Scenario: returns 400\n"
        "\n"
        "@error-handling\n"
        "Feature: POST /users\n"
    )
    # end_index candidate is the next Feature: header's index (line 6, 0-based 5)
    assert gherkin_text.trim_trailing_tag_run(lines, header_index=0, end_index=5) == 3


def test_trim_trailing_tag_run_stops_at_a_real_content_line():
    lines = _lines("Feature: POST /orders\n\n  Scenario: returns 400\n    Given x\n")
    assert gherkin_text.trim_trailing_tag_run(lines, header_index=0, end_index=4) == 4


def test_trim_trailing_tag_run_never_backs_up_past_the_header_line():
    lines = _lines("Feature: POST /orders\n\n\n")
    assert gherkin_text.trim_trailing_tag_run(lines, header_index=0, end_index=3) == 1
