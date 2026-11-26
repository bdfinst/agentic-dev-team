"""bash_segments — split a Bash command into evaluable segments.

Stdlib-only scanner (not `shlex.split`, which cannot see operators). It:

* splits on `;` `&&` `||` `|` `|&` `&` and newlines outside quotes;
* resolves single quotes, double quotes, and backslash escapes into words;
* lifts `$(...)`, backtick, and `( ... )` subshell bodies out as their own
  segments, and keeps `$((...))` arithmetic as opaque word text;
* skips heredoc bodies (they are data, not commands);
* records redirections apart from argv, resolving quoted targets;
* strips shell reserved words (`then`, `do`, `!`, `{`, ...) and wrappers
  (`time`, `env`, `nice`, `nohup`, `command`, `exec`, `builtin`, `timeout`,
  `xargs`) so a rule sees the real command;
* recurses into `bash|sh|zsh|dash [-opts] -c '<script>'`;
* fails closed: a segment whose real command or arguments cannot be known
  statically carries `opaque_reason` (command word unknown) or
  `untrusted_reason` (arguments or environment can change what runs), and a
  rule must never auto-allow either.

`parse(command)` raises `Unparseable` for an unbalanced quote, `$(`, `(`, or
backtick, so the caller can fail closed with a rewrite hint.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

_OPERATORS = ("&&", "||", "|&", ";", "|", "&")
_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_SUBSTITUTION_PLACEHOLDER = "$(...)"
_HEREDOC_DELIM_RE = re.compile(r"-?\s*(?:'([^']*)'|\"([^\"]*)\"|([^\s;&|<>()]+))")
_DYNAMIC_WORD_RE = re.compile(r"\$|\{[^{}]*,[^{}]*\}|\{\d+\.\.\d+\}")
_SHELL_CLUSTER_RE = re.compile(r"-[A-Za-z]+")
_MAX_DEPTH = 8
# `$` and `{` that quoting or escaping makes literal are swapped for private
# characters while scanning, so the expansion check sees only live ones.
_LITERAL_DOLLAR, _LITERAL_BRACE = "\ue001", "\ue002"

_RESERVED_WORDS = {"!", "{", "if", "then", "elif", "else", "while", "until", "do"}
_SHELLS = {"bash", "sh", "zsh", "dash"}

# wrapper -> (flags that consume the next word, flags that take no value).
# A flag outside both sets makes the segment untrusted: the value it would
# consume is unknown, so the command word cannot be told apart from it.
_WRAPPERS = {
    "time": ({"-o", "-f"}, {"-p", "-v", "-l", "-a"}),
    "nohup": (set(), set()),
    "command": (set(), {"-p"}),
    "exec": ({"-a"}, {"-c", "-l"}),
    "builtin": (set(), set()),
    "nice": ({"-n"}, set()),
    "env": (
        {"-u", "-C", "-S", "-P", "--unset", "--chdir", "--split-string"},
        {"-i", "-0", "-v", "--ignore-environment"},
    ),
    "timeout": (
        {"-s", "-k", "--signal", "--kill-after"},
        {"--foreground", "--preserve-status", "-v"},
    ),
    "xargs": (
        {
            "-I",
            "-n",
            "-P",
            "-d",
            "-L",
            "-s",
            "-E",
            "-a",
            "-J",
            "-R",
            "-S",
            "--arg-file",
            "--max-args",
            "--max-procs",
            "--delimiter",
            "--max-lines",
            "--max-chars",
            "--eof",
        },
        {
            "-0",
            "-r",
            "-t",
            "-p",
            "-x",
            "--null",
            "--no-run-if-empty",
            "--verbose",
            "--interactive",
            "--exit",
        },
    ),
}
# These change what runs or add arguments the rules never see.
_UNTRUSTED_WRAPPERS = {"env", "exec", "builtin", "xargs"}
_SPLIT_STRING_FLAGS = ("-S", "--split-string")


class Unparseable(ValueError):
    """The command cannot be segmented safely."""


@dataclass
class Segment:
    argv: list[str]
    redirects: list[str] = field(default_factory=list)
    opaque_reason: str = ""  # the command word cannot be known statically
    untrusted_reason: str = ""  # arguments or environment can change what runs

    @property
    def cmd(self) -> str:
        return os.path.basename(self.argv[0]) if self.argv else ""


def parse(command: str, _depth: int = 0) -> list[Segment]:
    """All segments of `command`, nested ones included, in source order."""
    if _depth > _MAX_DEPTH:
        raise Unparseable("command nests too deeply")
    segments: list[Segment] = []
    for words, redirects, nested in _scan(command):
        for sub in nested:
            segments.extend(parse(sub, _depth + 1))
        segment = _unwrap(words, redirects)
        if segment is None:
            continue
        script = _shell_script(segment.argv) if segment.cmd in _SHELLS else None
        if script is None:
            segments.append(segment)
            continue
        for inner in parse(script, _depth + 1):
            # `bash -c 'ls' > out` writes the file: the wrapper's redirects
            # and its untrusted environment apply to what it runs.
            inner.redirects.extend(segment.redirects)
            inner.untrusted_reason = (
                inner.untrusted_reason
                or segment.untrusted_reason
                or ("a path-qualified shell runs" if "/" in segment.argv[0] else "")
            )
            segments.append(inner)
    return segments


def _shell_script(argv: list[str]) -> str | None:
    """The `-c` script of `bash [-opts] -c <script>`, or None.

    `-c` counts only as an option before the first operand: after it, bash
    treats `-c` as an argument to a script file.
    """
    i = 1
    while i < len(argv):
        word = argv[i]
        if not word.startswith("-") or word == "-":
            return None
        if word in ("-o", "+o", "--rcfile", "--init-file"):
            i += 2
            continue
        if _SHELL_CLUSTER_RE.fullmatch(word) and "c" in word:
            return argv[i + 1] if i + 1 < len(argv) else None
        i += 1
    return None


def _literal(text: str) -> str:
    return text.replace("$", _LITERAL_DOLLAR).replace("{", _LITERAL_BRACE)


def _restore(text: str) -> str:
    return text.replace(_LITERAL_DOLLAR, "$").replace(_LITERAL_BRACE, "{")


def _skip_blanks(command: str, i: int) -> int:
    while i < len(command) and command[i] in " \t":
        i += 1
    return i


def _heredoc_delimiter(command: str, i: int) -> tuple[str, bool, bool, int]:
    """(delimiter, strip leading tabs, quoted, end index) of the word after `<<`.

    Quoted and unquoted parts join into one word, as bash does. A quoted
    delimiter makes the body literal; an unquoted one expands `$(...)` in it.
    """
    strip_tabs = command.startswith("-", i)
    start = _skip_blanks(command, i + 1 if strip_tabs else i)
    end, word = _read_word(command, start, [])
    delimiter = _restore(word)
    if not delimiter:
        raise Unparseable("empty heredoc delimiter")
    quoted = any(c in command[start:end] for c in "'\"\\")
    return delimiter, strip_tabs, quoted, end


def _arithmetic_end(command: str, i: int) -> int | None:
    """Index of the last `)` when the `$((` at `i` is arithmetic, else None.

    Bash reads it as arithmetic only when both parentheses close together;
    `$((cmd) )` is a command substitution that holds a subshell.
    """
    end = _matching_paren(command, i + 2, arith=True)
    return end if _matching_paren(command, i + 3, arith=True) == end - 1 else None


def _lift_substitution(command: str, i: int, nested: list[str]) -> int | None:
    """If a backtick or `$(` substitution starts at `i`, lift its body into
    `nested` and return the index after it; otherwise None."""
    if command[i] == "`":
        end = command.find("`", i + 1)
        if end < 0:
            raise Unparseable("unbalanced backtick")
        nested.append(command[i + 1 : end])
        return end + 1
    if command.startswith("$(", i) and not (
        command.startswith("$((", i) and _arithmetic_end(command, i) is not None
    ):
        end = _matching_paren(command, i + 2)
        nested.append(command[i + 2 : end])
        return end + 1
    return None


def _lift_embedded(body: str, nested: list[str]) -> None:
    """Lift every `$(...)`/backtick substitution inside arithmetic text."""
    i = 0
    while i < len(body):
        if body[i] == "\\":  # an escaped backtick or `$` is literal text
            i += 2
            continue
        lifted = _lift_substitution(body, i, nested)
        i = lifted if lifted is not None else i + 1


def _read_word(command: str, i: int, nested: list[str]) -> tuple[int, str]:
    """One shell word starting at `i` (quotes, escapes, substitutions resolved)."""
    out: list[str] = []
    n = len(command)
    while i < n and command[i] not in " \t\n;&|<>()":
        ch = command[i]
        if ch == "\\" and i + 1 < n:
            out.append(_literal(command[i + 1]))
            i += 2
        elif ch == "'":
            end = command.find("'", i + 1)
            if end < 0:
                raise Unparseable("unbalanced single quote")
            out.append(_literal(command[i + 1 : end]))
            i = end + 1
        elif ch == '"':
            i, text = _double_quoted(command, i, nested)
            out.append(text)
        else:
            lifted = _lift_substitution(command, i, nested)
            if lifted is not None:
                out.append(_SUBSTITUTION_PLACEHOLDER)
                i = lifted
            else:
                out.append(ch)
                i += 1
    return i, "".join(out)


def _read_redirect(command: str, i: int, fd_prefix: str, nested: list[str]):
    """Parse the redirect operator at `i`.

    Returns (new index, redirect text or None, heredoc delimiter or None).
    A redirect text of None means the operator wrote or read no file
    (`2>&1`, `>&-`).
    """
    n = len(command)
    j = i
    while j < n and (
        command[j] in "<>&" or (command[j] == "|" and command[j - 1] == ">")
    ):
        j += 1
    op = command[i:j]
    if op == "<<":
        delimiter, strip_tabs, quoted, end = _heredoc_delimiter(command, j)
        return end, "<<", (delimiter, strip_tabs, quoted)
    k = _skip_blanks(command, j)
    end, target = _read_word(command, k, nested)
    if op.endswith("&") and (target.isdigit() or target == "-"):
        return end, None, None
    return end, f"{fd_prefix}{op} {target}".strip(), None


def _scan(command: str):
    """Yield (words, redirects, nested_command_strings) per raw segment."""
    words: list[str] = []
    redirects: list[str] = []
    nested: list[str] = []
    word: list[str] = []
    has_word = False
    pending_heredocs: list[tuple[str, bool, bool]] = []
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
            bodies: list[str] = []
            i = _skip_heredocs(command, i + 1, pending_heredocs, bodies)
            pending_heredocs = []
            lifted_from_bodies: list[str] = []
            for body in bodies:
                _lift_embedded(body, lifted_from_bodies)
            if lifted_from_bodies:
                yield ([], [], lifted_from_bodies)
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
            if command[i + 1] != "\n":
                word.append(_literal(command[i + 1]))
                has_word = True
            i += 2
            continue
        if ch == "'":
            end = command.find("'", i + 1)
            if end < 0:
                raise Unparseable("unbalanced single quote")
            word.append(_literal(command[i + 1 : end]))
            has_word = True
            i = end + 1
            continue
        if ch == '"':
            i, text = _double_quoted(command, i, nested)
            word.append(text)
            has_word = True
            continue
        if command.startswith("$((", i) and (end := _arithmetic_end(command, i)):
            _lift_embedded(command[i + 3 : end], nested)
            word.append(command[i : end + 1])
            has_word = True
            i = end + 1
            continue
        lifted = _lift_substitution(command, i, nested)
        if lifted is not None:
            word.append(_SUBSTITUTION_PLACEHOLDER)
            has_word = True
            i = lifted
            continue
        op = next((o for o in _OPERATORS if command.startswith(o, i)), None)
        if op and not (op == "&" and command.startswith("&>", i)):
            seg = end_segment()
            if seg:
                yield seg
            i += len(op)
            continue
        if ch in "<>" or command.startswith("&>", i):
            fd_prefix = ""
            if has_word and "".join(word).isdigit():
                fd_prefix = "".join(word)
                word, has_word = [], False
            i, redirect, delimiter = _read_redirect(command, i, fd_prefix, nested)
            if redirect:
                redirects.append(redirect)
            if delimiter is not None:
                pending_heredocs.append(delimiter)
            continue
        if ch == "(" and not has_word:
            if command.startswith("((", i):
                raise Unparseable("arithmetic command ((...))")
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
            out.append(_literal(nxt) if nxt in '"\\$`' else "\\" + nxt)
            i += 2
            continue
        lifted = _lift_substitution(command, i, nested)
        if lifted is not None:
            out.append(_SUBSTITUTION_PLACEHOLDER)
            i = lifted
            continue
        out.append(_literal(ch) if ch == "{" else ch)
        i += 1
    raise Unparseable("unbalanced double quote")


def _matching_paren(command: str, start: int, arith: bool = False) -> int:
    """Index of the `)` closing a `(` whose body begins at `start`."""
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
        # Inside arithmetic, counting depth is enough, and recursing there
        # would rescan each nesting level repeatedly.
        if not arith and command.startswith("$((", i):
            end = _arithmetic_end(command, i)
            i = (_matching_paren(command, i + 2) if end is None else end) + 1
            continue
        if not arith and command.startswith("((", i):
            raise Unparseable("arithmetic command ((...))")
        if command.startswith("<<<", i):
            i += 3
            continue
        if not arith and command.startswith("<<", i):
            delimiter, strip_tabs, quoted, end = _heredoc_delimiter(command, i + 2)
            newline = command.find("\n", end)
            if newline >= 0:
                i = _skip_heredocs(
                    command, newline + 1, [(delimiter, strip_tabs, quoted)], []
                )
                continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise Unparseable("unbalanced $(")


def _skip_heredocs(
    command: str,
    i: int,
    delimiters: list[tuple[str, bool, bool]],
    bodies: list[str],
) -> int:
    """Index just past the bodies of `delimiters`, starting at line start `i`.

    A body ends on a line equal to its delimiter (leading tabs ignored for
    `<<-` only), as bash does. Bodies of unquoted heredocs are appended to
    `bodies`: bash expands `$(...)` in them.
    """
    for delim, strip_tabs, quoted in delimiters:
        body: list[str] = []
        while i < len(command):
            end = command.find("\n", i)
            line = command[i : end if end >= 0 else len(command)]
            i = end + 1 if end >= 0 else len(command)
            if (line.lstrip("\t") if strip_tabs else line) == delim:
                break
            body.append(line)
        if not quoted:
            bodies.append("\n".join(body))
    return i


def _strip_wrapper(argv: list[str]) -> tuple[list[str], str, str]:
    """Strip one wrapper and its options from the front of `argv`.

    Returns (rest, untrusted reason, opaque reason).
    """
    name = os.path.basename(argv[0])
    value_flags, bool_flags = _WRAPPERS[name]
    rest = argv[1:]
    untrusted = (
        f"{name} changes what runs or adds arguments"
        if name in _UNTRUSTED_WRAPPERS
        else ""
    )
    if "/" in argv[0]:
        untrusted = untrusted or f"{argv[0]} is a path-qualified wrapper"
    opaque = ""
    while rest:
        head = rest[0]
        flag = head.split("=", 1)[0]
        if (name == "timeout" and re.fullmatch(r"[\d.]+[smhd]?", head)) or (
            name == "env" and _ASSIGNMENT_RE.match(head)
        ):
            rest.pop(0)
        elif flag in value_flags:
            if name == "time":
                untrusted = untrusted or "time -o writes a file"
            if flag in _SPLIT_STRING_FLAGS and name == "env":
                opaque = "env -S runs a command string"
            rest = rest[1:] if "=" in head else rest[2:]
        elif name == "env" and head.startswith("-S"):
            opaque = "env -S runs a command string"
            rest.pop(0)
        elif flag in bool_flags:
            rest.pop(0)
        elif head.startswith("-") and len(head) > 1:
            untrusted = untrusted or f"{name} has an unrecognized option"
            rest.pop(0)
        else:
            break
    return rest, untrusted, opaque


# Variables whose assignment changes what later commands run or where they look.
_DANGEROUS_VARIABLE_RE = re.compile(
    r"^(PATH|IFS|BASH_ENV|ENV|SHELLOPTS|BASHOPTS|PS4|PROMPT_COMMAND|CDPATH|HOME|SHELL"
    r"|LD_\w*|DYLD_\w*|GIT_\w*|PYTHON\w*|NODE_\w*|XDG_\w*)="
)


def _finish(segment: Segment) -> Segment:
    segment.argv = [_restore(word) for word in segment.argv]
    segment.redirects = [_restore(r) for r in segment.redirects]
    return segment


def _unwrap(words: list[str], redirects: list[str]) -> Segment | None:
    argv = list(words)
    untrusted = ""
    dangerous_assignment = False
    while argv and _ASSIGNMENT_RE.match(argv[0]):
        dangerous_assignment = dangerous_assignment or bool(
            _DANGEROUS_VARIABLE_RE.match(argv[0])
        )
        argv.pop(0)
        untrusted = "an environment assignment prefix can change what runs"
    consumed_wrapper = False
    while argv:
        if argv[0] in _RESERVED_WORDS:
            argv.pop(0)
            continue
        name = os.path.basename(argv[0])
        if name not in _WRAPPERS:
            break
        if name == "command" and len(argv) > 1 and argv[1] in ("-v", "-V"):
            break
        consumed_wrapper = True
        argv, wrapper_untrusted, opaque = _strip_wrapper(argv)
        untrusted = untrusted or wrapper_untrusted
        if opaque:
            return _finish(Segment(list(words), redirects, opaque_reason=opaque))
    if not argv:
        if consumed_wrapper:
            return _finish(
                Segment(list(words), redirects, opaque_reason="wrapper with no command")
            )
        if dangerous_assignment:
            # A bare PATH=/LD_PRELOAD=/... changes every later command: never neutral.
            return _finish(Segment([], redirects, untrusted_reason=untrusted))
        return _finish(Segment([], redirects)) if redirects else None
    segment = Segment(argv, redirects, untrusted_reason=untrusted)
    if "$" in argv[0]:
        segment.opaque_reason = "the command word is a variable or substitution"
    elif any(_DYNAMIC_WORD_RE.search(word) for word in argv[1:]):
        segment.untrusted_reason = (
            segment.untrusted_reason or "an argument uses an expansion"
        )
    return _finish(segment)
