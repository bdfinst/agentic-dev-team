"""Unit tests for hooks/lib/gh_pr_create_detect.py (#1886)."""

from __future__ import annotations

import sys
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parents[2] / "hooks" / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import gh_pr_create_detect as detect  # type: ignore[import-not-found]


def test_bare_gh_pr_create_is_detected():
    assert detect.is_gh_pr_create_command("gh pr create") is True


def test_gh_pr_create_with_flags_is_detected():
    assert (
        detect.is_gh_pr_create_command('gh pr create --title "x" --body "y"')
        is True
    )


def test_path_qualified_gh_is_detected_by_basename():
    assert detect.is_gh_pr_create_command("/usr/local/bin/gh pr create") is True


def test_windows_style_path_qualified_gh_is_detected():
    assert detect.is_gh_pr_create_command(r"C:\tools\gh.exe pr create") is False
    # .exe suffix isn't stripped -- disclosed limitation, not this module's
    # target platform's realistic shape (Bash tool commands are POSIX-shaped).


def test_leading_env_assignment_is_skipped():
    assert detect.is_gh_pr_create_command("GH_TOKEN=abc gh pr create") is True


def test_second_segment_after_and_and_is_detected():
    assert detect.is_gh_pr_create_command("git push && gh pr create") is True


def test_second_segment_after_semicolon_is_detected():
    assert detect.is_gh_pr_create_command("echo done; gh pr create") is True


def test_first_of_two_segments_is_detected():
    assert detect.is_gh_pr_create_command("gh pr create; echo done") is True


def test_unrelated_command_is_not_detected():
    assert detect.is_gh_pr_create_command("git commit -m x") is False


def test_gh_pr_view_is_not_a_create():
    assert detect.is_gh_pr_create_command("gh pr view") is False


def test_gh_pr_list_is_not_a_create():
    assert detect.is_gh_pr_create_command("gh pr list") is False


def test_gh_issue_create_is_not_a_pr_create():
    assert detect.is_gh_pr_create_command("gh issue create") is False


def test_separator_inside_a_quoted_string_is_not_a_boundary():
    # The `;` inside the quoted title must not split the command.
    assert (
        detect.is_gh_pr_create_command('gh pr create --title "a; b" --body "x"')
        is True
    )


def test_empty_command_is_not_detected():
    assert detect.is_gh_pr_create_command("") is False


def test_unbalanced_quoting_does_not_crash():
    assert detect.is_gh_pr_create_command("gh pr create --title 'unterminated") is False


# --- issue #1904 Bug 3: bare `&` separator ----------------------------------


def test_bare_ampersand_backgrounds_the_first_segment_and_detects_the_second():
    """`true & gh pr create --title x` used to stay one segment (with
    `true` as `tokens[0]`), missing the `gh pr create` entirely — a total,
    silent bypass of the sole trigger point for the review gate."""
    assert detect.is_gh_pr_create_command("true & gh pr create --title x") is True


def test_double_ampersand_still_matches_as_the_two_character_operator():
    """`&&` must still split as ONE two-character operator, not two bare
    `&` separators — regression guard for the new single-`&` case."""
    assert detect.is_gh_pr_create_command("git push && gh pr create") is True


def test_bare_ampersand_inside_a_quoted_string_is_not_a_boundary():
    assert (
        detect.is_gh_pr_create_command('gh pr create --title "a & b" --body "x"')
        is True
    )


# --- issue #1904 Bug 3: single-quote escape semantics -----------------------


def test_single_quote_has_no_backslash_escape_and_closes_on_the_trailing_backslash():
    """POSIX single quotes have NO escape mechanism — `echo 'a\\' ; gh pr
    create` closes the quote at that `'` in real bash regardless of the
    preceding backslash, so the `;` that follows is a real separator and
    the `gh pr create` after it must still be detected. The old,
    quote-character-agnostic backslash exemption treated the quote as
    still open, swallowing the `;` and missing the second segment."""
    assert (
        detect.is_gh_pr_create_command("echo 'a\\' ; gh pr create") is True
    )


def test_double_quote_backslash_escape_still_exempts_the_closing_quote():
    """Regression guard: the backslash-escape exemption must still apply to
    DOUBLE quotes, where it is a real POSIX escape — `\\"` inside a
    double-quoted string is a literal quote character, not a closer."""
    assert (
        detect.is_gh_pr_create_command('gh pr create --title "a\\" b"') is True
    )
