"""Unit tests for hooks/lib/pre_commit_detect.py (#576 / #572 Cluster B).

Byte-parity with hooks/lib/pre-commit-detect.sh — the .sh's
`_is_git_commit_invocation` is the whole exported surface.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HOOKS_LIB = Path(__file__).resolve().parents[2] / "hooks" / "lib"
if str(_HOOKS_LIB) not in sys.path:
    sys.path.insert(0, str(_HOOKS_LIB))

import pre_commit_detect as detect  # type: ignore[import-not-found]


@pytest.mark.parametrize(
    "cmd",
    [
        "git commit",
        "git commit -m 'hi'",
        "  git   commit  -a -m foo",
        "git commit --amend",
        "\tgit commit\t-m x",
    ],
)
def test_detects_git_commit(cmd: str) -> None:
    assert detect.is_git_commit_invocation(cmd) is True


@pytest.mark.parametrize(
    "cmd",
    [
        "",
        "echo git commit",
        "git status",
        "git-commit",  # hyphen, not a subcommand
        "gitcommit",
        "pipx run git-commit",
        "notgit commit",
        "git commitment",  # word-boundary must reject
        # bypass
        "git commit --no-verify",
        "git commit -m x --no-verify",
        "  git commit  --no-verify -m x",
    ],
)
def test_rejects_non_gates(cmd: str) -> None:
    assert detect.is_git_commit_invocation(cmd) is False


def test_no_verify_bypass_substring_matches_sh() -> None:
    """--no-verify is the documented bypass; parity with the .sh requires
    substring match — `--no-verify` inside `--no-verifying` also bypasses.
    A future author who wants word-boundary bypass should update both
    implementations together (this port owes byte-parity, not opinions)."""
    assert detect.is_git_commit_invocation("git commit --no-verify") is False
    # Substring match — matches the .sh's plain grep behavior.
    assert detect.is_git_commit_invocation("git commit --no-verifying") is False


# --- #709: bare `-n` parity with `--no-verify` -----------------------------


@pytest.mark.parametrize(
    "cmd",
    [
        "git commit -n -m x",
        "git commit -m x -n",
        "  git commit  -n  -m x",
        "git commit -n",
    ],
)
def test_bare_n_is_a_bypass_like_no_verify(cmd: str) -> None:
    assert detect.is_git_commit_invocation(cmd) is False
    assert detect.has_bypass_flag(cmd) is True


@pytest.mark.parametrize(
    "cmd",
    [
        "git commit -m x",
        "git commit -na -m x",  # not a bare -n token
        "git commit --amend -na",
    ],
)
def test_non_bare_n_is_not_a_bypass(cmd: str) -> None:
    assert detect.has_bypass_flag(cmd) is False


def test_is_git_commit_command_ignores_bypass_flags() -> None:
    """Unlike is_git_commit_invocation, is_git_commit_command answers
    "is this a git commit at all" regardless of any bypass flag — callers
    that need to react to bypassed commits (rather than silently ignore
    them) use this plus has_bypass_flag."""
    assert detect.is_git_commit_command("git commit --no-verify -m x") is True
    assert detect.is_git_commit_command("git commit -n -m x") is True
    assert detect.is_git_commit_command("git status") is False


def test_bypass_flag_name() -> None:
    assert detect.bypass_flag_name("git commit -m x") is None
    assert detect.bypass_flag_name("git commit -n -m x") == "-n"
    assert detect.bypass_flag_name("git commit --no-verify -m x") == "--no-verify"
    # Both present — --no-verify preferred.
    assert detect.bypass_flag_name("git commit --no-verify -n -m x") == "--no-verify"


# --- independent security-review finding (#1761/#1762/#1763 Slice 3 build):
# equivalent commit invocations that used to skip the gate with zero trace.


@pytest.mark.parametrize(
    "cmd",
    [
        "git -C /some/repo commit -m x",
        "git -c user.name=x commit -m x",
        "git --git-dir=/some/repo/.git commit -m x",
        "cd sub && git commit -m x",
        "env X=1 git commit -m x",
        "bash -c 'git commit -m x'",
    ],
)
def test_detects_equivalent_commit_invocations(cmd: str) -> None:
    assert detect.is_git_commit_command(cmd) is True


def test_still_rejects_non_gates_with_widened_detection() -> None:
    # Widened detection must not regress the original negatives.
    assert detect.is_git_commit_command("echo git commit") is False
    assert detect.is_git_commit_command("git status") is False
    assert detect.is_git_commit_command("git commitment") is False
    assert detect.is_git_commit_command("pipx run git-commit") is False


# --- #1801 second round: correctness-review + security-review both FAILED
# the first (regex-only) attempt at the widening above. These pin the
# specific adversarial forms that attempt confirmed as false negatives, now
# closed by shlex-tokenizing each segment instead of regex-matching raw text.


@pytest.mark.parametrize(
    "cmd",
    [
        'git "commit" -m x',  # quoted subcommand
        "'git' commit -m x",  # quoted command word
        "\\git commit -m x",  # backslash-escaped command word
        "X=1 git commit -m x",  # bare assignment, no `env` keyword
        "FOO=1 git commit -m x",
        "git --git-dir /some/repo/.git commit -m x",  # space-separated long option
        "git -c core.pager commit -m x",  # valueless -c (boolean true)
        "git add . & git commit -m x",  # single `&` (background) separator
        "if true; then git commit -m x; fi",  # compound-command keyword
        "exec git commit -m x",  # exec wrapper
        "sudo git commit -m x",  # sudo wrapper
        'git -C "/a b" commit -m x',  # quoted -C value containing whitespace
        'git -c user.name="A B" commit -m x',
        "git -C ~/repo commit -m x",  # tilde in -C value
    ],
)
def test_detects_quoting_and_wrapper_evasion_forms(cmd: str) -> None:
    assert detect.is_git_commit_command(cmd) is True


@pytest.mark.parametrize(
    "cmd",
    [
        # The narrowed shell-`-c` quote scan must not flag ordinary
        # commands that merely mention "git commit" inside a quoted
        # string — the first version's blanket quote scan did, an
        # undisclosed blast radius correctness-review flagged.
        'grep -rn "git commit" docs/',
        'echo "run git commit -m x"',
        "echo 'a; git commit'",
    ],
)
def test_quoted_mentions_outside_a_shell_c_wrapper_are_not_flagged(cmd: str) -> None:
    assert detect.is_git_commit_command(cmd) is False


# --- #1801 third round: correctness-review + security-review both FAILED the
# second (per-segment shlex-tokenizing) attempt too — splitting on raw-string
# separator characters BEFORE tokenizing let a quoted separator inside a git
# option's value bisect the invocation, and the narrowed shell-`-c` regex
# couldn't see a clustered shell flag (`bash -lc`). Closed by tokenizing each
# physical line ONCE (quote-aware) and splitting on the resulting SEPARATOR
# TOKENS instead of raw characters.


@pytest.mark.parametrize(
    "cmd",
    [
        'git -c user.name="A; B" commit -m x',  # quoted `;` in a git-option value
        'git -c "core.pager=less|cat" commit -m x',  # quoted `|`
        'bash -lc "git commit -m x"',  # clustered shell flag ending in c
        'sh -ec "git commit -m x"',
        'zsh -ic "git commit -m x"',
        "sudo -u dev git commit -m x",  # wrapper word carrying its own option
        "nice -n 10 git commit -m x",
        "env -i git commit -m x",
        "true || git commit -m x",  # `||` separator
        "cd sub && git commit -m x",  # `&&` separator via the new tokenizer path
    ],
)
def test_detects_third_round_evasion_forms(cmd: str) -> None:
    assert detect.is_git_commit_command(cmd) is True


@pytest.mark.parametrize(
    "cmd",
    [
        # A quoted separator inside an UNRELATED command's string must not
        # get bisected into a false match either (the over-block direction
        # of the same underlying fix).
        'echo "stage then: git add . ; git commit -m msg"',
        # `-o pipefail` before `-c` is a disclosed residual gap (a wrapper
        # option taking a separate-token value this module doesn't model)
        # — pinned here as documented current behavior, not asserted as
        # correct, so a future change to it is a deliberate decision.
        "bash -o pipefail -c 'git commit -m x'",
    ],
)
def test_third_round_negatives_and_disclosed_gaps(cmd: str) -> None:
    assert detect.is_git_commit_command(cmd) is False


def test_extract_shell_dash_c_bodies_recurses_into_multiline_nested_command() -> None:
    """A `bash -c` argument that itself contains multiple newline-separated
    commands must still be scanned line-by-line for a nested commit."""
    assert (
        detect.is_git_commit_command("bash -c 'echo hi\ngit commit -m x'") is True
    )


@pytest.mark.parametrize(
    "cmd",
    [
        # Backtick and NUL-byte -C values used to be exercised via
        # resolve_commit_targets() (deleted #1904, orphaned once its sole
        # caller — pre_commit_review.py's per-target commit-gating — was
        # retired to a no-op by #1886). Detection itself is unaffected by
        # what -C's value contains.
        "git -C '`whoami`' commit -m x",
        "git -C \"a\x00b\" commit -m x",
        # A value-taking global option other than -c, exercised in both its
        # separate-token and `=`-attached forms.
        "git --namespace foo commit -m x",
        "git --exec-path=/usr/lib/git-core commit -m x",
    ],
)
def test_detects_commits_with_value_taking_global_options(cmd: str) -> None:
    assert detect.is_git_commit_command(cmd) is True


def test_decoy_redirect_segment_still_detected_as_a_commit() -> None:
    """Re-pin the second/third-round decoy-redirect finding's DETECTION
    half (target RESOLUTION was `resolve_commit_targets()`, deleted #1904):
    every matching segment in a multi-segment command must still be found,
    not just the first."""
    assert (
        detect.is_git_commit_command(
            "git -C /tmp/decoy commit --allow-empty -m x; git commit -m real"
        )
        is True
    )


# --- #1801 fourth round: security-review + correctness-review both found
# real false negatives in the third round's tokenize-once-per-line design
# too — a re-enabled shlex comment stripper, separator tokens glued to
# adjacent punctuation, path-qualified interpreters, one-level-only nesting
# despite the docstring claiming recursion, a shared (rather than per-
# wrapper) value-taking-option table, and a per-line split that broke a
# multi-line quoted value while a bare newline with no line-split at all
# would have missed a second real commit on its own line.


@pytest.mark.parametrize(
    "cmd",
    [
        "true a#b; git commit -m x",  # unquoted `#` must not truncate the line
        "true;(git commit -m x)",  # separator glued to adjacent punctuation
        "true && (git commit -m x)",
        "echo hi |& git commit -m x",
        "(git status)&&(git commit -m x)",
        '/bin/bash -c "git commit -m x"',  # path-qualified interpreter
        "/bin/bash -lc \"git commit -m x\"",
        "/usr/bin/git commit -m x",
        "/usr/bin/sudo git commit -m x",
        "bash -c \"bash -c 'git commit -m x'\"",  # nested one level deeper
        "sudo -n git commit -m x",  # sudo's -n is boolean, not value-taking
        "sudo -n -u dev git commit -m x",
        "git status\ngit commit -m x",  # bare newline as a real separator
    ],
)
def test_detects_fourth_round_evasion_forms(cmd: str) -> None:
    assert detect.is_git_commit_command(cmd) is True


def test_multiline_quoted_message_with_leading_semicolon_still_detected() -> None:
    """The third round's per-line pre-split broke exactly this shape: a
    semicolon on the SAME physical line as the start of a multi-line
    quoted `-m` message made that line fail to tokenize (unbalanced
    quote), and the naive-split fallback then lost the semicolon as a
    recognized separator token entirely."""
    assert (
        detect.is_git_commit_command(
            'git add -A; git commit -m "line1\nline2"'
        )
        is True
    )


def test_fourth_round_negatives_and_disclosed_gaps() -> None:
    # `-o pipefail` (a separate-value option) before `-c` remains a
    # disclosed gap — pinned as documented current behavior, not asserted
    # as correct, so a future change to it is a deliberate decision.
    assert detect.is_git_commit_command("bash -o pipefail -c 'git commit -m x'") is False


# --- #1801 fifth round: a closing-pass re-review found an error-severity
# bug in the fourth round's own fix (`_mask_bare_newlines` preserved a
# POSIX line-continuation pair verbatim instead of deleting it, exactly
# like a real shell does) plus several genuinely new, narrower evasion
# forms now explicitly disclosed in KNOWN RESIDUAL GAPS rather than fixed
# (redirection before the command word, command substitution, `env -S`,
# a clustered shell flag with `c` not last, and bypass-flag detection
# staying quote-unaware) — a regex/token heuristic converges but never
# fully completes; see this module's own docstring.


@pytest.mark.parametrize(
    "cmd",
    [
        "git add -A && \\\ngit commit -m x",  # line continuation before &&
        "git \\\ncommit -m x",  # line continuation splitting git/commit
        "setsid git commit -m x",
        "doas git commit -m x",
    ],
)
def test_detects_fifth_round_evasion_forms(cmd: str) -> None:
    assert detect.is_git_commit_command(cmd) is True


def test_line_continuation_does_not_break_a_real_escaped_character() -> None:
    """The line-continuation fix must not regress ordinary backslash-
    escaping of a non-newline character."""
    assert detect.is_git_commit_command(r"\git commit -m x") is True


@pytest.mark.parametrize(
    "cmd",
    [
        # Redirection before the command word, command substitution, and
        # `env -S` are disclosed residual gaps (KNOWN RESIDUAL GAPS item 5
        # in pre_commit_review.py), pinned here as documented CURRENT
        # behavior rather than asserted as correct.
        ">/dev/null git commit -m x",
        "2>&1 git commit -m x",
        "echo $(git commit -m x)",
        "env -S 'git commit -m x'",
    ],
)
def test_fifth_round_disclosed_gaps(cmd: str) -> None:
    assert detect.is_git_commit_command(cmd) is False


# --- #1801 sixth round: a final gate-corroboration pass found two more
# convergent (both security-review and correctness-review independently
# raised the `doas` one), cheap, well-specified bugs: `doas` was added to
# `_WRAPPER_WORDS` without a matching `_WRAPPER_VALUE_TAKING_OPTS` entry
# (unlike its sibling `sudo`), and `_match_commit_tokens` decided "was
# this option's value `=`-attached?" from the TRUTHINESS of the
# partitioned value rather than whether `=` was actually present — an
# option with a present-but-EMPTY attached value (`--namespace=`) was
# misparsed as needing a separate-token value and swallowed `commit`.


@pytest.mark.parametrize(
    "cmd",
    [
        "doas -u dev git commit -m x",
        "doas -u dev -C /tmp git commit -m x",
        "time -o /tmp/t git commit -m x",
    ],
)
def test_detects_sixth_round_wrapper_option_forms(cmd: str) -> None:
    assert detect.is_git_commit_command(cmd) is True


@pytest.mark.parametrize(
    "cmd",
    [
        "git --namespace= commit -m x",  # present but empty attached value
        "git --exec-path= commit -m x",
        "git -C= commit -m x",
    ],
)
def test_empty_attached_value_does_not_swallow_commit(cmd: str) -> None:
    assert detect.is_git_commit_command(cmd) is True
