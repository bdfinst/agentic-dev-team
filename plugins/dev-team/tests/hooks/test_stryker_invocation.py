"""Unit tests for hooks/lib/stryker_invocation.py (#2185).

The shared predicate both C# mutation gates use to decide "does this command
actually RUN Stryker.NET" — parsed, not scanned, so a mention of the tool
name in a --body/grep/echo/comment argument is never mistaken for an
invocation.
"""

from __future__ import annotations

import sys

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_LIB = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"
sys.path.insert(0, str(_LIB))

import stryker_invocation as si


@pytest.mark.parametrize(
    "cmd",
    [
        "dotnet stryker",
        "dotnet stryker --mutate src/Foo.cs",
        "  dotnet   stryker  ",
        "dotnet-stryker",
        "dotnet-stryker --reporter json",
        "cd repo && dotnet stryker --config-file config.json",
        "cd tests/Acme.Widgets.Tests.Mutation && dotnet-stryker",
        "true && dotnet stryker --mutate x.cs",
        "bash plugins/dev-team/hooks/mutation-adapters/csharp-stryker-net-wrapper.sh --arg",
        "/abs/path/to/csharp-stryker-net-wrapper.sh",
        "csharp_stryker_net_wrapper",
    ],
)
def test_matches_real_invocations(cmd: str) -> None:
    assert si.is_stryker_invocation(cmd) is True


@pytest.mark.parametrize(
    "cmd",
    [
        "",
        "echo hi",
        "dotnet build",
        "dotnetstryker",  # no boundary
        "pip install stryker",
        'gh issue create --body "the docs say to run dotnet stryker -t mtp here"',
        "grep -rn 'dotnet stryker' docs/",
        'echo "never run dotnet stryker on main"',
        'python3 -c "# dotnet stryker"',
    ],
)
def test_ignores_non_invocations(cmd: str) -> None:
    assert si.is_stryker_invocation(cmd) is False


def test_heredoc_body_mentioning_tool_name_does_not_trigger() -> None:
    cmd = (
        "gh issue create --title x --body-file - <<'EOF'\n"
        "the docs say to run dotnet stryker here\n"
        "EOF"
    )
    assert si.is_stryker_invocation(cmd) is False


def test_unbalanced_quotes_fail_closed_to_permissive_scan() -> None:
    # shlex can't tokenize this (unterminated quote) — fall back to the old
    # permissive regex, which still finds the real invocation, rather than
    # silently letting a malformed command through unblocked.
    assert si.is_stryker_invocation("dotnet stryker --config 'unclosed") is True


def test_unbalanced_quotes_without_the_tool_name_still_pass() -> None:
    assert si.is_stryker_invocation("echo 'unclosed") is False
