"""bash_segments — split a Bash command into evaluable segments.

Stdlib-only scanner (not `shlex.split`, which cannot see operators). It:

* splits on `;` `&&` `||` `|` `|&` `&` and newlines outside quotes;
* resolves single quotes, double quotes, and backslash escapes into words;
* lifts `$(...)`, backtick, and `( ... )` subshell bodies out as their own
  segments;
* skips heredoc bodies (they are data, not commands);
* records redirections apart from argv;
* strips wrappers (`time`, `env`, `nice`, `nohup`, `command`, `exec`,
  `builtin`, `timeout`, `xargs`) so the rule sees the real command;
* recurses into `bash|sh|zsh -c '<script>'`;
* flags a command word that is a variable expansion as opaque.

`parse(command)` raises `Unparseable` for an unbalanced quote, `$(`, or
backtick, so the caller can fail closed with a rewrite hint.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

_OPERATORS = ("&&", "||", "|&", ";", "|", "&")
_REDIRECT_RE = re.compile(r"^(\d*|&)(>>?|<<?<?|>&|<&)$")
_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_MAX_DEPTH = 8

# Wrapper -> option flags that consume the next word.
_WRAPPER_VALUE_FLAGS = {
    "time": set(),
    "nohup": set(),
    "command": set(),
    "exec": set(),
    "builtin": set(),
    "nice": {"-n"},
    "env": {"-u", "-C", "-S"},
    "timeout": {"-s", "-k"},
    "xargs": {"-I", "-n", "-P", "-d", "-L", "-s", "-E", "-a"},
}
_SHELLS = {"bash", "sh", "zsh", "dash"}


class Unparseable(ValueError):
    """The command cannot be segmented safely."""


@dataclass
class Segment:
    argv: list[str]
    redirects: list[str] = field(default_factory=list)
    opaque: str = ""  # reason the command word cannot be known statically

    @property
    def cmd(self) -> str:
        return os.path.basename(self.argv[0]) if self.argv else ""


def parse(command: str, _depth: int = 0) -> list[Segment]:
    """All segments of `command`, nested ones included, in source order."""
    if _depth > _MAX_DEPTH:
        raise Unparseable("command nests too deeply")
    segments: list[Segment] = []
    for words, redirects, nested in _scan(command, _depth):
        for sub in nested:
            segments.extend(parse(sub, _depth + 1))
        segment = _unwrap(words, redirects)
        if segment is None:
            continue
        if segment.cmd in _SHELLS and "-c" in segment.argv[1:]:
            idx = segment.argv.index("-c")
            if idx + 1 < len(segment.argv):
                segments.extend(parse(segment.argv[idx + 1], _depth + 1))
                continue
        segments.append(segment)
    return segments


def _scan(command: str, depth: int):
    """Yield (words, redirects, nested_command_strings) per raw segment."""
    words: list[str] = []
    redirects: list[str] = []
    nested: list[str] = []
    word: list[str] = []
    has_word = False
    pending_heredocs: list[str] = []
    i, n = 0, len(command)

    def end_word():
        nonlocal word, has_word
        if has_word:
            words.append("".join(word))
        word, has_word = [], False

    def end_segment():
        nonlocal words, redirects, nested
        end_word()
        out = (words, redirects, nested) if (words or redirects or nested) else None
        words, redirects, nested = [], [], []
        return out

    while i < n:
        ch = command[i]
        if ch == "\n" and pending_heredocs:
            seg = end_segment()
            if seg:
                yield seg
            i = _skip_heredocs(command, i + 1, pending_heredocs)
            pending_heredocs = []
            continue
        if ch in " \t":
            end_word()
            i += 1
            continue
        if ch == "\n":
            seg = end_segment()
            if seg:
                yield seg
            i += 1
            continue
        if ch == "#" and not has_word:
            while i < n and command[i] != "\n":
                i += 1
            continue
        if ch == "\\":
            if i + 1 >= n:
                raise Unparseable("trailing backslash")
            if command[i + 1] == "\n":
                i += 2
                continue
            word.append(command[i + 1])
            has_word = True
            i += 2
            continue
        if ch == "'":
            end = command.find("'", i + 1)
            if end < 0:
                raise Unparseable("unbalanced single quote")
            word.append(command[i + 1 : end])
            has_word = True
            i = end + 1
            continue
        if ch == '"':
            i, text = _double_quoted(command, i, nested)
            word.append(text)
            has_word = True
            continue
        if ch == "`":
            end = command.find("`", i + 1)
            if end < 0:
                raise Unparseable("unbalanced backtick")
            nested.append(command[i + 1 : end])
            word.append("$(...)")
            has_word = True
            i = end + 1
            continue
        if ch == "$" and command.startswith("$(", i) and not command.startswith("$((", i):
            end = _matching_paren(command, i + 2)
            nested.append(command[i + 2 : end])
            word.append("$(...)")
            has_word = True
            i = end + 1
            continue
        op = next((o for o in _OPERATORS if command.startswith(o, i)), None)
        if op and not _is_redirect_amp(command, i, op):
            seg = end_segment()
            if seg:
                yield seg
            i += len(op)
            continue
        if ch in "<>" or (ch == "&" and command.startswith("&>", i)):
            end_word_text = "".join(word) if has_word and "".join(word).isdigit() else None
            if end_word_text is not None:
                word, has_word = [], False
            j = i
            while j < n and command[j] in "<>&":
                j += 1
            token = (end_word_text or "") + command[i:j]
            if command.startswith("<<", i) and not command.startswith("<<<", i):
                k = j
                while k < n and command[k] in " \t":
                    k += 1
                m = re.match(r"-?\s*(?:'([^']*)'|\"([^\"]*)\"|([^\s;&|<>()]+))", command[k:])
                if m:
                    pending_heredocs.append(m.group(1) or m.group(2) or m.group(3))
                    k += m.end()
                redirects.append("<<")
                i = k
                continue
            k = j
            while k < n and command[k] in " \t":
                k += 1
            m = re.match(r"[^\s;&|<>()]+", command[k:])
            target = m.group(0) if m else ""
            if token.endswith("&") and target.isdigit():
                pass  # fd duplication such as 2>&1: no file written
            else:
                redirects.append(f"{token} {target}".strip())
            i = k + (m.end() if m else 0)
            continue
        if ch == "(" and not has_word:
            end = _matching_paren(command, i + 1)
            nested.append(command[i + 1 : end])
            i = end + 1
            continue
        if ch in "()":
            raise Unparseable("unbalanced or unsupported parenthesis")
        word.append(ch)
        has_word = True
        i += 1
    seg = end_segment()
    if seg:
        yield seg


def _is_redirect_amp(command: str, i: int, op: str) -> bool:
    """`&` that belongs to `>&`, `<&`, or `&>` rather than backgrounding."""
    if op != "&":
        return False
    return (i > 0 and command[i - 1] in "<>") or command.startswith("&>", i)


def _double_quoted(command: str, i: int, nested: list[str]) -> tuple[int, str]:
    out: list[str] = []
    i += 1
    n = len(command)
    while i < n:
        ch = command[i]
        if ch == '"':
            return i + 1, "".join(out)
        if ch == "\\" and i + 1 < n:
            nxt = command[i + 1]
            out.append(nxt if nxt in '"\\$`' else "\\" + nxt)
            i += 2
            continue
        if ch == "`":
            end = command.find("`", i + 1)
            if end < 0:
                raise Unparseable("unbalanced backtick")
            nested.append(command[i + 1 : end])
            out.append("$(...)")
            i = end + 1
            continue
        if ch == "$" and command.startswith("$(", i) and not command.startswith("$((", i):
            end = _matching_paren(command, i + 2)
            nested.append(command[i + 2 : end])
            out.append("$(...)")
            i = end + 1
            continue
        out.append(ch)
        i += 1
    raise Unparseable("unbalanced double quote")


def _matching_paren(command: str, start: int) -> int:
    """Index of the `)` closing a `$(` whose body begins at `start`."""
    depth, i, n = 1, start, len(command)
    while i < n:
        ch = command[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "'":
            end = command.find("'", i + 1)
            if end < 0:
                break
            i = end + 1
            continue
        if ch == '"':
            i += 1
            while i < n and command[i] != '"':
                i += 2 if command[i] == "\\" else 1
            i += 1
            continue
        if command.startswith("<<", i) and not command.startswith("<<<", i):
            m = re.match(r"<<-?\s*(?:'([^']*)'|\"([^\"]*)\"|([^\s;&|<>()]+))", command[i:])
            if m:
                delim = m.group(1) or m.group(2) or m.group(3)
                newline = command.find("\n", i)
                if newline >= 0:
                    i = _skip_heredocs(command, newline + 1, [delim])
                    continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise Unparseable("unbalanced $(")


def _skip_heredocs(command: str, i: int, delimiters: list[str]) -> int:
    """Index just past the bodies of `delimiters`, starting at line start `i`."""
    for delim in delimiters:
        while i < len(command):
            end = command.find("\n", i)
            line = command[i : end if end >= 0 else len(command)]
            i = end + 1 if end >= 0 else len(command)
            if line.strip() == delim:
                break
    return i


def _unwrap(words: list[str], redirects: list[str]) -> Segment | None:
    argv = list(words)
    while argv and _ASSIGNMENT_RE.match(argv[0]):
        argv.pop(0)
    while argv:
        name = os.path.basename(argv[0])
        if name not in _WRAPPER_VALUE_FLAGS:
            break
        value_flags = _WRAPPER_VALUE_FLAGS[name]
        argv.pop(0)
        while argv:
            head = argv[0]
            if head in value_flags:
                del argv[:2]
            elif name == "timeout" and not head.startswith("-") and re.fullmatch(r"[\d.]+[smhd]?", head) or name == "env" and _ASSIGNMENT_RE.match(head) or head.startswith("-") and len(head) > 1:
                argv.pop(0)
            else:
                break
    if not argv:
        return Segment([], redirects) if redirects else None
    segment = Segment(argv, redirects)
    if "$" in argv[0]:
        segment.opaque = "the command word is a variable or substitution"
    return segment
