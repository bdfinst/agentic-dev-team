#!/usr/bin/env python3
"""Shared predicate: does a shell command actually RUN Stryker.NET? (#2185)

Both C# mutation PreToolUse gates (`mutation_testing_smoke_gate.py` and
`stryker_xunit_shim_guard.py`) used to decide "is this a Stryker run?" with a
bare `re.search` over the entire command string — no notion of argument
position, quoting, or comments. Any command that merely *mentioned* the tool
name in prose (a `gh issue create --body "..."`, a `grep`, an `echo`, a
Python comment) was treated as an invocation and blocked.

This module parses the command instead of scanning it: tokenize with
`shlex.shlex(..., punctuation_chars=True)` (posix quoting rules, `&&`/`||`/
`;`/`|` recognised as their own tokens), split the token stream into
per-operator segments, and match the tool only in **program position** of a
segment — `dotnet` with `stryker` as its very next token, a bare
`dotnet-stryker` token, or the wrapper script (however it's invoked: directly,
or via an interpreter like `bash <path>` — matched by exact basename, not
substring, so a quoted prose mention that happens to contain the wrapper's
name cannot collide with a real path token).

Heredoc bodies are stripped before tokenizing (`<<EOF ... EOF` /
`<<'EOF' ... EOF` / `<<-EOF ... EOF`) — a command that pipes documentation
prose through a heredoc is the same false-positive shape as a quoted
argument, just harder for `shlex` to see through structurally.

Fails closed: if `shlex` raises (unbalanced quotes it cannot tokenize), fall
back to the old permissive regex over the raw command rather than silently
returning False — a malformed command still gets caught rather than sliding
through unblocked.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

#: Matches only when shlex tokenization itself fails — the pre-#2185
#: permissive scan, kept as the fail-closed fallback for unparseable input.
_FALLBACK_TRIGGER = re.compile(
    r"(?:^|[^a-zA-Z0-9])dotnet[ \t-]+stryker(?:\b|$)|csharp[_-]stryker[_-]net[_-]wrapper"
)

#: Shell operators that separate one command segment from the next. `>`/`<`
#: (redirects) deliberately excluded — they don't start a new program.
_SEGMENT_OPERATORS = {"&&", "||", ";", "|"}

#: A `<<[-]DELIM ... DELIM` heredoc body, DELIM optionally quoted.
_HEREDOC_RE = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?\n.*?\n\1\b", re.DOTALL)

#: The plugin's Stryker.NET wrapper script, matched against a token's
#: basename — with or without hyphen/underscore separators, with or without
#: the `.sh` extension (mirrors the two gates' previously-divergent forms).
_WRAPPER_NAME_RE = re.compile(r"^csharp[_-]stryker[_-]net[_-]wrapper(\.sh)?$")


def _strip_heredocs(command: str) -> str:
    return _HEREDOC_RE.sub("", command)


def _segments(tokens: list[str]) -> list[list[str]]:
    segments: list[list[str]] = [[]]
    for tok in tokens:
        if tok in _SEGMENT_OPERATORS:
            segments.append([])
        else:
            segments[-1].append(tok)
    return [seg for seg in segments if seg]


def _segment_is_stryker(segment: list[str]) -> bool:
    if not segment:
        return False
    first = segment[0]
    if first == "dotnet" and len(segment) > 1 and segment[1] == "stryker":
        return True
    if first == "dotnet-stryker":
        return True
    # The wrapper, invoked directly or via an interpreter (`bash <path>`,
    # `sh <path>`) — only the program and its immediate first argument can
    # be the wrapper path, so later arguments are never checked.
    for tok in segment[:2]:
        if _WRAPPER_NAME_RE.match(Path(tok).name):
            return True
    return False


def is_stryker_invocation(command: str) -> bool:
    """True only when `command` actually runs Stryker.NET — `dotnet stryker`,
    `dotnet-stryker`, or the plugin's wrapper script, in program position of
    one of the command's operator-separated segments. A mention of the tool
    name in a --body/grep/echo/comment argument does not count."""
    if not command:
        return False
    stripped = _strip_heredocs(command)
    try:
        lexer = shlex.shlex(stripped, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return bool(_FALLBACK_TRIGGER.search(command))
    return any(_segment_is_stryker(seg) for seg in _segments(tokens))
