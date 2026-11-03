"""Examiner read audit for the acceptance examiner (#2270).

Pure, stdlib only, no I/O, no filesystem lookups. Classifies the Bash commands
the examiner ran and reports each forbidden read of a repository path, each
state-changing command, and each git read or write subcommand.

This is a denylist: pattern detection over the command text, not proof. It can
false-positive (a pattern that looks like a path) and false-negative (a quoted
`|`, `&&`, `>`, or `<` is read as the shell operator). Multi-line commands are
tokenized with newlines as whitespace, not separators. Interpreter-based reads (`python3 -c`,
`node -e`, `find -exec`, `xargs` with a non-reader) are deliberately
unaudited, as are commands outside the sets below. A finding means "detected by
pattern"; an empty result does not mean the run was clean.

Paths resolve lexically against the effective cwd (`cd` is tracked within one
command); a path is "inside the repository" when it is `root` or under `root`.
Paths ending `.feature` and absolute paths outside `root` are never findings.
Findings report the operand as written. Command strings are untrusted model
output: they are tokenized and compared, never executed.
"""

from __future__ import annotations

import posixpath
import re
import shlex
from typing import NamedTuple

KIND_READ = "read"
KIND_WRITE = "write"
KIND_GIT = "git"
KIND_XARGS = "xargs"

READERS = frozenset(
    {
        "cat",
        "head",
        "tail",
        "sed",
        "less",
        "more",
        "awk",
        "cut",
        "grep",
        "rg",
        "strings",
        "bat",
        "nl",
        "sort",
        "diff",
        "xxd",
        "od",
        "wc",
        "jq",
    }
)
GIT_READ = frozenset({"show", "diff", "log", "cat-file", "grep", "blame"})
#: Commands whose repo-path operands are writes. `sed -i` is a write too and is
#: handled in `_classify_command`; redirects `>` and `>>` in `_split_redirects`.
WRITERS = frozenset({"tee", "rm", "mv", "cp"})
GIT_WRITE = frozenset(
    {
        "commit",
        "checkout",
        "switch",
        "reset",
        "stash",
        "apply",
        "rm",
        "mv",
        "restore",
        "clean",
        "push",
        "add",
        "config",
        "merge",
        "rebase",
        "branch",
        "tag",
        "update-ref",
    }
)

#: Readers whose first non-flag operand is a pattern or script, not a path,
#: unless `-e` or `-f` supplied it.
_PATTERN_FIRST = frozenset({"grep", "rg", "sed", "awk", "jq"})
_PATTERN_FLAGS = frozenset({"-e", "-f"})
_PATTERN_VALUE_FLAGS = frozenset({"-m", "-A", "-B", "-C", "-e", "-f"})
#: Short flags that consume the next token, per reader. Readers not listed take
#: no value flags (`tail -f` follows; `wc -m` counts characters).
_VALUE_FLAGS = {
    "grep": _PATTERN_VALUE_FLAGS,
    "rg": _PATTERN_VALUE_FLAGS,
    "sed": _PATTERN_VALUE_FLAGS,
    "awk": _PATTERN_VALUE_FLAGS,
    "head": frozenset({"-n", "-c"}),
    "tail": frozenset({"-n", "-c"}),
    "cut": frozenset({"-d", "-f"}),
}
_XARGS_VALUE_FLAGS = frozenset({"-I", "-n", "-P", "-L", "-s", "-E", "-d", "-a"})
_GIT_VALUE_FLAGS = frozenset({"-C", "-c"})

_SEPARATORS = frozenset({"&&", "||", ";", "|"})
FEATURE_SUFFIX = ".feature"
_STDIN_OPERAND = "-"
_UNKNOWN_CWD = None

#: `[fd]<op>[target]`; `&>` and `&>>` redirect both streams. `<<` and `<<<`
#: are heredoc forms whose next word is a delimiter, never a file.
_REDIRECT = re.compile(r"^(\d*|&)(<<<|<<|>>|>&|<&|>|<)(.*)$")
_FD_TARGET = re.compile(r"^(\d+-?|-)$")
_DIGITS = re.compile(r"^\d+$")
_HEREDOC_OPS = frozenset({"<<", "<<<"})
_FD_DUP_OPS = frozenset({">&", "<&"})


class Finding(NamedTuple):
    """One audit hit. `target` is the operand as written, the git subcommand,
    or the xargs'd reader name; `command` is the full original command."""

    kind: str
    target: str
    command: str


class _Scope(NamedTuple):
    root: str
    cwd: str | None


def audit_commands(commands: list[str], root: str, cwd: str) -> list[Finding]:
    """Return the findings for `commands`, in command then segment order.

    Each command starts from `cwd`: the Bash tool resets cwd between calls.
    """
    root = posixpath.normpath(root)
    start = posixpath.normpath(cwd)
    return [
        Finding(kind, target, command)
        for command in commands
        for kind, target in _audit_command(command, root, start)
    ]


def _audit_command(command: str, root: str, cwd: str | None) -> list[tuple[str, str]]:
    hits: list[tuple[str, str]] = []
    for segment in _segments(_tokenize(command)):
        words, redirects = _split_redirects(segment)
        if words and words[0] == "cd":
            cwd = _next_cwd(words[1:], cwd)
        hits.extend(_classify_segment(words, redirects, _Scope(root, cwd)))
    return hits


def _tokenize(command: str) -> list[str]:
    """Shell-like tokens with `&&`, `||`, `;`, `|`, `<`, `>` split out.

    Falls back to a whitespace split (quote characters stripped) when the
    quoting is unbalanced.
    """
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        return list(lexer)
    except ValueError:
        return [word.strip("'\"") for word in command.split()]


def _segments(tokens: list[str]) -> list[list[str]]:
    """Token lists per simple command. Pipe position has no effect on the
    operand rules (a stdin filter has no path operand), so it is not kept."""
    segments: list[list[str]] = [[]]
    for token in tokens:
        if token in _SEPARATORS:
            segments.append([])
        else:
            segments[-1].append(token)
    return [segment for segment in segments if segment]


def _split_redirects(segment: list[str]) -> tuple[list[str], list[tuple[str, str]]]:
    """Split a segment into its words and its file redirects.

    Redirects are `(op, target)` with op `<` (read) or `>` (write). Fd
    duplications (`2>&1`, `>&2`) and heredoc delimiters are dropped.
    """
    words: list[str] = []
    redirects: list[tuple[str, str]] = []
    tokens = iter(segment)
    for token in tokens:
        match = _REDIRECT.match(token)
        if match is None:
            words.append(token)
            continue
        prefix, op, target = match.groups()
        if not prefix and words and _DIGITS.match(words[-1]):
            words.pop()  # `2` of a split `2 >` is an fd prefix, not a word
        target = target or next(tokens, "")
        if op in _HEREDOC_OPS:
            continue
        if op in _FD_DUP_OPS and _FD_TARGET.match(target):
            continue
        redirects.append(("<" if op.startswith("<") else ">", target))
    return words, redirects


def _next_cwd(args: list[str], cwd: str | None) -> str | None:
    """Lexical cwd after `cd`. Home, `-`, and variable targets are unknown,
    which is treated as outside the repository."""
    operands = _operands(args)
    if not operands:
        return _UNKNOWN_CWD
    target = operands[0]
    if (
        target.startswith("~")
        or target == _STDIN_OPERAND
        or "$" in target
        or "`" in target
    ):
        return _UNKNOWN_CWD
    if posixpath.isabs(target):
        return posixpath.normpath(target)
    if cwd is _UNKNOWN_CWD:
        return _UNKNOWN_CWD
    return posixpath.normpath(posixpath.join(cwd, target))


def _classify_segment(
    words: list[str], redirects: list[tuple[str, str]], scope: _Scope
) -> list[tuple[str, str]]:
    hits = _classify_command(words[0], words[1:], scope) if words else []
    for op, target in redirects:
        if _is_repo_path(target, scope):
            hits.append((KIND_READ if op == "<" else KIND_WRITE, target))
    return hits


def _classify_command(
    name: str, args: list[str], scope: _Scope
) -> list[tuple[str, str]]:
    if name == "git":
        return _classify_git(args)
    if name == "xargs":
        reader = _xargs_reader(args)
        return [(KIND_XARGS, reader)] if reader else []
    if name in WRITERS:
        return _repo_hits(KIND_WRITE, _operands(args), scope)
    if name in READERS:
        kind = KIND_WRITE if name == "sed" and _is_in_place(args) else KIND_READ
        return _repo_hits(kind, _reader_operands(name, args), scope)
    return []


def _classify_git(args: list[str]) -> list[tuple[str, str]]:
    subcommand = _git_subcommand(args)
    if subcommand in GIT_READ or subcommand in GIT_WRITE:
        return [(KIND_GIT, subcommand)]
    return []


def _git_subcommand(args: list[str]) -> str | None:
    skip_value = False
    for arg in args:
        if skip_value:
            skip_value = False
        elif arg in _GIT_VALUE_FLAGS:
            skip_value = True
        elif not arg.startswith("-"):
            return arg
    return None


def _xargs_reader(args: list[str]) -> str | None:
    """The reader `xargs` runs, or None when it runs anything else."""
    skip_value = False
    for arg in args:
        if skip_value:
            skip_value = False
        elif arg in _XARGS_VALUE_FLAGS:
            skip_value = True
        elif not arg.startswith("-"):
            return arg if arg in READERS else None
    return None


def _is_in_place(args: list[str]) -> bool:
    return any(arg.startswith(("-i", "--in-place")) for arg in args)


def _operands(args: list[str]) -> list[str]:
    """Non-flag tokens; a lone `-` counts as an operand."""
    return [arg for arg in args if arg == _STDIN_OPERAND or not arg.startswith("-")]


def _reader_operands(name: str, args: list[str]) -> list[str]:
    """Candidate path operands of a reader, after flag values and the leading
    pattern or script are removed."""
    value_flags = _VALUE_FLAGS.get(name, frozenset())
    operands: list[str] = []
    has_pattern_flag = False
    skip_value = False
    flags_ended = False
    for arg in args:
        if skip_value:
            skip_value = False
        elif flags_ended or arg == _STDIN_OPERAND or not arg.startswith("-"):
            operands.append(arg)
        elif arg == "--":
            flags_ended = True
        else:
            has_pattern_flag = has_pattern_flag or arg in _PATTERN_FLAGS
            skip_value = arg in value_flags
    if name in _PATTERN_FIRST and not has_pattern_flag:
        return operands[1:]
    return operands


def _repo_hits(kind: str, operands: list[str], scope: _Scope) -> list[tuple[str, str]]:
    return [(kind, operand) for operand in operands if _is_repo_path(operand, scope)]


def _is_repo_path(operand: str, scope: _Scope) -> bool:
    if not operand or operand == _STDIN_OPERAND or operand.startswith("~"):
        return False
    if operand.endswith(FEATURE_SUFFIX):
        return False
    if posixpath.isabs(operand):
        resolved = posixpath.normpath(operand)
    elif scope.cwd is _UNKNOWN_CWD:
        return False
    else:
        resolved = posixpath.normpath(posixpath.join(scope.cwd, operand))
    return resolved == scope.root or resolved.startswith(scope.root.rstrip("/") + "/")
