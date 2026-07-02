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

import pre_commit_detect as detect  # type: ignore[import-not-found]  # noqa: E402


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
