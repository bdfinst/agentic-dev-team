"""Find shell calls in SKILL.md text and judge whether they can hang on stdin.

Neutral helper: it knows nothing about which scripts read stdin. Callers pass
``(script basename, input flag)`` pairs.

A call is scanned in two places:

- a fenced block tagged ``bash``, ``sh`` or ``shell`` (untagged fences and
  other tags are ignored), one logical line at a time (backslash
  continuations joined, heredoc bodies skipped);
- an inline-code span outside any fence.

Inside a command, a call starts at a segment (split on ``|``, ``||``, ``&&``,
``;``, ``&``) that begins with ``python3`` or with a path containing ``/``
whose basename is the script. Plain ``python``, a bare script name
(``change_impact.py`` with no ``/`` and no ``python3``), and an inline span that
is only a path with no arguments are mentions, not calls. Direct path
execution inside a scanned fence is a call.

A call is safe when it has any of the script's input flags (exact token or
``--flag=value``; a script may have several), is the target of a pipe (``|`` before it, or the previous
logical line ends with ``|``), or has a ``<``, ``<<`` or ``<<<`` redirect
after it. A pipe after the call never excuses it.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import NamedTuple

SCANNED_FENCE_TAGS = frozenset({"bash", "sh", "shell"})

_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})\s*([\w+-]*)")
_INLINE_RE = re.compile(r"`([^`\n]+)`")
# `<changed files>` style placeholders, which are not input redirects.
_PLACEHOLDER_RE = re.compile(r"<[A-Za-z][^<>|&;\n]*[^\s<>|&;]>")
_ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_SEGMENT_OPS = frozenset({"|", "||", "&&", ";", "&"})
_REDIRECT_OPS = frozenset({"<", "<<", "<<<"})


class Command(NamedTuple):
    file: str
    line: int
    command_text: str
    preceding_line: str
    is_inline: bool


class Offender(NamedTuple):
    file: str
    line: int
    script: str
    command_text: str


def iter_commands(file: str, text: str) -> Iterator[Command]:
    """Yield every fenced logical line and inline-code span in ``text``."""
    lines = text.splitlines()
    fence_marker: str | None = None
    fence_scanned = False
    block: list[tuple[int, str]] = []

    for number, raw in enumerate(lines, start=1):
        match = _FENCE_RE.match(raw)
        if fence_marker is None:
            if match:
                fence_marker = match.group(1)
                fence_scanned = match.group(2).lower() in SCANNED_FENCE_TAGS
                block = []
                continue
            for span in _INLINE_RE.finditer(raw):
                yield Command(file, number, span.group(1).strip(), "", True)
            continue
        closes = (
            match
            and match.group(1)[0] == fence_marker[0]
            and len(match.group(1)) >= len(fence_marker)
            and not match.group(2)
        )
        if closes:
            if fence_scanned:
                yield from _fenced_commands(file, block)
            fence_marker = None
            continue
        block.append((number, raw))


def _fenced_commands(file: str, block: list[tuple[int, str]]) -> Iterator[Command]:
    logical: list[tuple[int, str]] = []
    pending: tuple[int, str] | None = None
    for number, raw in block:
        if pending is not None:
            start, joined = pending
            joined += " " + raw.strip()
        else:
            start, joined = number, raw.strip()
        if joined.endswith("\\"):
            pending = (start, joined[:-1].rstrip())
            continue
        pending = None
        logical.append((start, joined))
    if pending is not None:
        logical.append(pending)

    previous = ""
    heredoc_end: str | None = None
    for start, text in logical:
        if heredoc_end is not None:
            if text == heredoc_end:
                heredoc_end = None
            continue
        if not text or text.startswith("#"):
            continue
        yield Command(file, start, text, previous, False)
        previous = text
        heredoc_end = _heredoc_delimiter(text)


def _heredoc_delimiter(text: str) -> str | None:
    match = re.search(r"<<-?\s*(?:'([^']+)'|\"([^\"]+)\"|(\w+))", text)
    if match is None or "<<<" in text:
        return None
    return match.group(1) or match.group(2) or match.group(3)


def tokenize(text: str) -> list[str]:
    cleaned = _PLACEHOLDER_RE.sub("PLACEHOLDER", text)
    lexer = shlex.shlex(cleaned, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = "#"
    try:
        return list(lexer)
    except ValueError:
        # Unbalanced quote (an apostrophe in prose): fall back to a crude split.
        return cleaned.replace('"', " ").replace("'", " ").split()


def split_segments(tokens: list[str]) -> Iterator[tuple[str, list[str]]]:
    """Yield ``(separator before, tokens)`` for each command segment."""
    separator = ""
    current: list[str] = []
    for token in tokens:
        if token in _SEGMENT_OPS:
            if current:
                yield separator, current
            separator, current = token, []
        else:
            current.append(token)
    if current:
        yield separator, current


def _call_script(segment: list[str], inline: bool) -> str | None:
    """Return the script basename if the segment is a call, else None."""
    words = list(segment)
    while words and _ENV_ASSIGN_RE.match(words[0]):
        words.pop(0)
    if not words:
        return None
    if words[0] == "python3":
        words.pop(0)
        while words and words[0].startswith("-") and words[0] != "-":
            words.pop(0)
        if not words:
            return None
        return words[0].rsplit("/", 1)[-1]
    if "/" in words[0] and not (inline and len(words) == 1):
        return words[0].rsplit("/", 1)[-1]
    return None


def has_flag(args: Iterable[str], flag: str) -> bool:
    return any(arg == flag or arg.startswith(flag + "=") for arg in args)


def unguarded_calls(
    command: Command, scripts: Iterable[tuple[str, str]]
) -> list[Offender]:
    """Return the calls in ``command`` that can hang on stdin.

    ``scripts`` holds ``(script basename, input flag)`` pairs; a script may
    appear in several pairs, one per flag.
    """
    flags: dict[str, set[str]] = {}
    for name, flag in scripts:
        flags.setdefault(name, set()).add(flag)
    offenders: list[Offender] = []
    parts = list(split_segments(tokenize(command.command_text)))
    for index, (separator, segment) in enumerate(parts):
        name = _call_script(segment, command.is_inline)
        if name not in flags:
            continue
        piped = separator == "|" or (
            index == 0 and command.preceding_line.rstrip().endswith("|")
        )
        redirected = any(token in _REDIRECT_OPS for token in segment)
        flagged = any(has_flag(segment, flag) for flag in flags[name])
        if piped or redirected or flagged:
            continue
        offenders.append(
            Offender(command.file, command.line, name, command.command_text)
        )
    return offenders


def find_offenders(
    file: str, text: str, scripts: Iterable[tuple[str, str]]
) -> list[Offender]:
    pairs = list(scripts)
    found: list[Offender] = []
    for command in iter_commands(file, text):
        found.extend(unguarded_calls(command, pairs))
    return found


def find_offenders_in_files(
    paths: Iterable[Path], scripts: Iterable[tuple[str, str]]
) -> list[Offender]:
    pairs = list(scripts)
    found: list[Offender] = []
    for path in paths:
        found.extend(find_offenders(str(path), path.read_text(encoding="utf-8"), pairs))
    return found
