"""Find shell calls in SKILL.md text and judge whether they can hang on stdin.

Neutral helper: it knows nothing about which scripts read stdin. Callers pass
``InputFlag`` rules (or ``(script basename, input flag)`` pairs).

A call is scanned in two places:

- a fenced block tagged ``bash``, ``sh`` or ``shell`` (untagged fences and
  other tags are ignored), one logical line at a time (backslash
  continuations joined, heredoc bodies skipped);
- an inline-code span outside any fence.

Inside a command, a call starts at a segment (split on ``|``, ``||``, ``&&``,
``;``, ``&``) that begins with ``python3``, with the launcher form
``sh|bash <path>/py.sh <script-path>``, or with a path containing ``/`` whose
basename is the script. Leading ``(``, ``$(``, ``then``, ``do`` and ``time``
words are skipped, as are env assignments. Plain ``python``, a bare script
name (``change_impact.py`` with no ``/`` and no ``python3``), and an inline
span that is only a path with no arguments are mentions, not calls. Direct path
execution inside a scanned fence is a call. A ``#`` comment (unquoted, at the
start of a word) is dropped before tokenizing.

A call is safe when it has one of the script's applicable input flags (exact
token or ``--flag=value``, with a value other than ``-``, which means stdin; a
script may have several, and a rule may apply only to some ``--mode`` values),
is the target of a pipe (``|`` before it, or the previous
logical line ends with ``|``), or has a ``<``, ``<<`` or ``<<<`` redirect
after it. A pipe after the call never excuses it.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

SCANNED_FENCE_TAGS = frozenset({"bash", "sh", "shell"})

_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})\s*([\w+-]*)")
_INLINE_RE = re.compile(r"`([^`\n]+)`")
# `<changed files>` style placeholders, which are not input redirects.
_PLACEHOLDER_RE = re.compile(r"<[A-Za-z][^<>|&;\n]*[^\s<>|&;]>")
#: What a ``<changed files>`` style placeholder becomes in a tokenized command.
PLACEHOLDER_TOKEN = "PLACEHOLDER"
_ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_SEGMENT_OPS = frozenset({"|", "||", "&&", ";", "&"})
_REDIRECT_OPS = frozenset({"<", "<<", "<<<"})
#: Words that can sit between a segment start and the command it runs.
_PREFIX_WORDS = frozenset({"(", "$", "$(", "then", "do", "time", "else", "if", "!", "{"})
_SHELL_LAUNCHERS = frozenset({"sh", "bash"})
_PY_LAUNCHER = "py.sh"


@dataclass(frozen=True)
class InputFlag:
    """One flag that makes ``script`` read a file instead of stdin.

    With ``mode_option`` set, the rule applies only when that option's value
    (or ``default_mode`` when the option is absent) is in ``modes``.
    """

    script: str
    flag: str
    mode_option: str | None = None
    modes: tuple[str, ...] = ()
    default_mode: str | None = None


class Command(NamedTuple):
    file: str
    line: int
    command_text: str
    preceding_line: str
    is_inline: bool


class CallSite(NamedTuple):
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
    if fence_marker is not None and fence_scanned:
        yield from _fenced_commands(file, block)


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


def strip_comment(text: str) -> str:
    """Drop a trailing ``#`` comment: an unquoted ``#`` that starts a word."""
    quote = ""
    for index, char in enumerate(text):
        if quote:
            if char == quote:
                quote = ""
        elif char in "'\"":
            quote = char
        elif char == "#" and (index == 0 or text[index - 1].isspace()):
            return text[:index].rstrip()
    return text


def tokenize(text: str) -> list[str]:
    cleaned = _PLACEHOLDER_RE.sub(PLACEHOLDER_TOKEN, strip_comment(text))
    lexer = shlex.shlex(cleaned, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
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
    while words and (_ENV_ASSIGN_RE.match(words[0]) or words[0] in _PREFIX_WORDS):
        words.pop(0)
    if not words:
        return None
    if words[0] in _SHELL_LAUNCHERS and len(words) > 1:
        words.pop(0)
    if words[0].rsplit("/", 1)[-1] == _PY_LAUNCHER:
        return words[1].rsplit("/", 1)[-1] if len(words) > 1 else None
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


def option_value(args: list[str], option: str) -> str | None:
    """Value of ``option`` (``--opt value`` or ``--opt=value``), else None."""
    for index, arg in enumerate(args):
        if arg == option:
            return args[index + 1] if index + 1 < len(args) else ""
        if arg.startswith(option + "="):
            return arg[len(option) + 1 :]
    return None


def has_file_valued_flag(args: list[str], flag: str) -> bool:
    """True when ``flag`` is given a value other than ``-`` (stdin)."""
    value = option_value(args, flag)
    return value is not None and value != "-"


def _applies(rule: InputFlag, segment: list[str]) -> bool:
    if rule.mode_option is None:
        return True
    mode = option_value(segment, rule.mode_option)
    return (rule.default_mode if mode is None else mode) in rule.modes


def _rules_by_script(
    input_flags: Iterable[InputFlag | tuple[str, str]],
) -> dict[str, list[InputFlag]]:
    rules: dict[str, list[InputFlag]] = {}
    for item in input_flags:
        rule = item if isinstance(item, InputFlag) else InputFlag(*item)
        rules.setdefault(rule.script, []).append(rule)
    return rules


def judge_calls(
    command: Command, input_flags: Iterable[InputFlag | tuple[str, str]]
) -> list[tuple[CallSite, bool]]:
    """Return every call to a listed script in ``command`` as
    ``(call, safe)``: ``safe`` is False when the call can hang on stdin.

    ``input_flags`` holds one ``InputFlag`` (or ``(script basename, flag)`` pair)
    per input flag; a script may appear several times.
    """
    rules_by_script = _rules_by_script(input_flags)
    judged: list[tuple[CallSite, bool]] = []
    parts = list(split_segments(tokenize(command.command_text)))
    for index, (separator, segment) in enumerate(parts):
        name = _call_script(segment, command.is_inline)
        if name not in rules_by_script:
            continue
        piped = separator == "|" or (
            index == 0 and command.preceding_line.rstrip().endswith("|")
        )
        redirected = any(token in _REDIRECT_OPS for token in segment)
        flagged = any(
            _applies(rule, segment) and has_file_valued_flag(segment, rule.flag)
            for rule in rules_by_script[name]
        )
        call = CallSite(command.file, command.line, name, command.command_text)
        judged.append((call, piped or redirected or flagged))
    return judged


def unguarded_calls(
    command: Command, input_flags: Iterable[InputFlag | tuple[str, str]]
) -> list[CallSite]:
    """Return the calls in ``command`` that can hang on stdin."""
    return [call for call, safe in judge_calls(command, input_flags) if not safe]


def find_calls(
    file: str, text: str, input_flags: Iterable[InputFlag | tuple[str, str]]
) -> list[tuple[CallSite, bool]]:
    """Every call to a listed script in ``text``, safe or not."""
    listed = list(input_flags)
    found: list[tuple[CallSite, bool]] = []
    for command in iter_commands(file, text):
        found.extend(judge_calls(command, listed))
    return found


def find_offenders(
    file: str, text: str, input_flags: Iterable[InputFlag | tuple[str, str]]
) -> list[CallSite]:
    listed = list(input_flags)
    found: list[CallSite] = []
    for command in iter_commands(file, text):
        found.extend(unguarded_calls(command, listed))
    return found


def find_offenders_in_files(
    paths: Iterable[Path], input_flags: Iterable[InputFlag | tuple[str, str]]
) -> list[CallSite]:
    listed = list(input_flags)
    found: list[CallSite] = []
    for path in paths:
        found.extend(find_offenders(str(path), path.read_text(encoding="utf-8"), listed))
    return found
