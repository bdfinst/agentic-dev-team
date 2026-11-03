"""Examiner read audit for the acceptance examiner (#2270).

Pure, stdlib only, no I/O, no filesystem lookups. Classifies the Bash commands
the examiner ran and reports each forbidden read of a repository path, each
state-changing command, and each git read or write subcommand.

This is a denylist: detection is by pattern over the command text, not proof.
A finding means "detected by pattern" and can be a false positive. An empty
result does not mean the run was clean. What the audit does NOT cover:

- Operands built by the shell are unknown and are never findings: any word
  with an unquoted-literal `$` or a backtick (`cat "$f"`, `> "${TMPDIR}/x"`),
  and any glob or substitution result. This is an accepted false negative.
  (Command substitutions and process substitutions are audited as nested
  commands, to a recursion depth of 3. A heredoc body is not parsed, except
  that an unquoted delimiter (`<<EOF`) makes the `$(...)` and backtick spans
  in the body nested commands; a quoted one (`<<'EOF'`) is never parsed.)
- Symlinks (made with `ln` or otherwise), case-insensitive filesystems, and
  sibling git worktrees: paths resolve lexically against `root` only.
- Interpreter-based reads (`python3 -c`, `node -e`, `bash script.sh`,
  `find -exec`, `xargs` with a non-reader), wrappers such as `sudo`, git
  aliases from config or the environment, and commands outside the sets below.
- `pushd`/`popd`; `cd` inside a subshell or a branch is treated as persisting.

Paths resolve lexically against the effective cwd (`cd` is tracked within one
command); a path is "inside the repository" when it is `root` or under `root`.
After a `cd` whose target cannot be resolved lexically (`cd ~`, `cd -`, bare
`cd`, `cd $VAR`), relative operands are treated as inside the repository: a
false positive is preferred to an unaudited read. A home-tilde operand (`~`,
`~/x`, `~user/x`) is treated the same way, because the home directory may
contain the repository. Paths ending `.feature` are
exempt from reads only, and absolute paths outside `root` are never findings.
Findings report the operand as written. Command strings are untrusted model
output: they are lexed and compared, never executed.
"""

from __future__ import annotations

import posixpath
import re
from itertools import pairwise
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
        "tac",
        "base64",
        "paste",
        "rev",
        "fold",
        "pr",
        "hexdump",
        "uniq",
        "comm",
        "cmp",
        "vim",
        "view",
    }
)
GIT_READ = frozenset(
    {
        "show",
        "diff",
        "log",
        "cat-file",
        "grep",
        "blame",
        "annotate",
        "whatchanged",
        "format-patch",
        "archive",
        "range-diff",
        "diff-tree",
        "diff-index",
        "diff-files",
        "fast-export",
    }
)
#: Commands whose repo-path operands are writes. `sed -i` is a write too and is
#: handled in `_classify_command`; redirects in `_redirect_kind`.
WRITERS = frozenset({"tee", "rm", "mv", "cp"})
#: `branch`, `tag`, `remote`, `worktree`, `symbolic-ref`, and `config` are
#: write-capable, but each has read-only forms that `_is_read_only_git_form`
#: exempts; every other form of them is a finding.
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
        "merge",
        "rebase",
        "update-ref",
        "branch",
        "tag",
        "remote",
        "worktree",
        "symbolic-ref",
        "config",
    }
)
#: Flags and keywords that leave a write-capable git verb read-only.
_GIT_READ_ONLY_FLAGS = frozenset({"--list", "-l", "-v", "-a", "--show-current"})
_GIT_LISTING_ONLY_FLAGS = frozenset({"--list", "-l"})
_GIT_LISTING_KEYWORD_BY_VERB = {"remote": "show", "worktree": "list"}
_GIT_LISTING_VERBS = frozenset({"branch", "tag", "remote", "worktree"})
_GIT_CONFIG_READ_FLAGS = frozenset(
    {"--list", "-l", "--get", "--get-all", "--get-regexp"}
)
_GIT_CONFIG_SCOPE_FLAGS = frozenset(
    {"--local", "--global", "--system", "--worktree", "--show-origin", "--show-scope"}
)
_GIT_SYMBOLIC_REF_FLAGS = frozenset({"-q", "--quiet", "--short", "--no-recurse"})

_CMD_CD = "cd"
_CMD_GIT = "git"
_CMD_XARGS = "xargs"
_CMD_SED = "sed"
_CMD_DD = "dd"
_DD_INPUT_PREFIX = "if="
_CMD_GREP = "grep"
_CMD_RG = "rg"
_CMD_EVAL = "eval"
_CMD_TIMEOUT = "timeout"
_SHELLS = frozenset({"bash", "sh", "dash", "zsh"})
_GIT_ALIAS_TARGET = "alias"

#: Words that precede the real command and are dropped before classifying it.
_PREFIX_WORDS = frozenset(
    {"!", "{", "}", "do", "then", "else", "elif", "if", "while", "until"}
)
_WRAPPERS = frozenset(
    {"env", "command", "builtin", "exec", "nice", "nohup", "time", "timeout"}
)
_WRAPPER_VALUE_FLAGS = {
    "env": frozenset({"-u", "-C"}),
    "nice": frozenset({"-n"}),
    "timeout": frozenset({"-s", "-k"}),
    "exec": frozenset({"-a"}),
}
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\+?=")

_PATTERN_FLAGS_COMMON = frozenset({"-e", "-f", "--regexp", "--file", "--expression"})
#: Readers whose first non-flag operand is a pattern or script, not a path,
#: unless one of these flags supplied it (also in attached form: `-e.`,
#: `--regexp=.`).
_PATTERN_FLAGS = {
    "grep": _PATTERN_FLAGS_COMMON,
    "rg": _PATTERN_FLAGS_COMMON,
    "sed": _PATTERN_FLAGS_COMMON,
    "awk": _PATTERN_FLAGS_COMMON,
    "jq": frozenset({"-f", "--from-file"}),
}
_PATTERN_READER_VALUE_FLAGS = frozenset(
    {
        "-m",
        "-A",
        "-B",
        "-C",
        "-e",
        "-f",
        "--max-count",
        "--after-context",
        "--before-context",
        "--context",
        "--regexp",
        "--file",
        "--expression",
    }
)
#: jq flags that bind a name: they consume two following tokens.
_JQ_BINDING_FLAGS = frozenset({"--arg", "--argjson", "--slurpfile", "--rawfile"})
#: Flags that consume the next token, per reader. Readers not listed take no
#: value flags (`tail -f` follows; `wc -m` counts characters).
_VALUE_FLAGS = {
    "grep": _PATTERN_READER_VALUE_FLAGS | {"-d", "--directories"},
    "rg": _PATTERN_READER_VALUE_FLAGS,
    "sed": _PATTERN_READER_VALUE_FLAGS,
    "awk": _PATTERN_READER_VALUE_FLAGS | {"-F", "-v"},
    "jq": _JQ_BINDING_FLAGS,
    "head": frozenset({"-n", "-c"}),
    "tail": frozenset({"-n", "-c"}),
    "cut": frozenset({"-d", "-f"}),
    "sort": frozenset({"-k", "-t"}),
    "fold": frozenset({"-w"}),
    "base64": frozenset({"-w"}),
    "uniq": frozenset({"-f", "-s", "-w"}),
    "tac": frozenset({"-s"}),
    "paste": frozenset({"-d"}),
    "cmp": frozenset({"-n", "-i"}),
    "hexdump": frozenset({"-n", "-s", "-e"}),
}
_XARGS_VALUE_FLAGS = frozenset({"-I", "-n", "-P", "-L", "-s", "-E", "-d", "-a"})
_GIT_VALUE_FLAGS = frozenset(
    {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
    | {"--super-prefix"}
)

_IMPLICIT_OPERAND = "."
_GREP_RECURSIVE_FLAGS = frozenset(
    {"-r", "-R", "--recursive", "--dereference-recursive", "--directories=recurse"}
    | {"-drecurse"}
)
_GREP_DIRECTORIES_FLAGS = frozenset({"-d", "--directories"})
_GREP_RECURSE = "recurse"
_GREP_VALUE_LETTERS = frozenset("efmABCd")

FEATURE_SUFFIX = ".feature"
_STDIN_OPERAND = "-"
_END_OF_FLAGS = "--"
_MAX_DEPTH = 3
_GLOB_CHARS = re.compile(r"[*?\[{]")
_PROC_SELF_CWD = "/proc/self/cwd"

# Operators, longest first. `_SEPARATORS` split commands; the rest redirect.
_OPERATORS = (
    "<<<",
    "<<-",
    "&>>",
    "<<",
    ">>",
    "<>",
    "<&",
    ">&",
    ">|",
    "&>",
    "&&",
    "||",
    "|&",
    "<",
    ">",
    "|",
    ";",
    "&",
    "(",
    ")",
)
_SEPARATORS = frozenset({"&&", "||", "|&", ";", "|", "&", "\n", "(", ")"})
_PIPES = frozenset({"|", "|&"})
_HEREDOC_OPS = frozenset({"<<", "<<-"})
#: Redirects whose next word is a literal, never a file.
_NO_FILE_OPS = frozenset({"<<", "<<-", "<<<"})
_READ_REDIRECTS = frozenset({"<", "<&"})
_FD_DUP_OPS = frozenset({">&", "<&"})
_FD_TARGET = re.compile(r"^(\d+-?|-)$")
_DOUBLE_QUOTE_ESCAPES = frozenset({'"', "\\", "$", "`"})

_Hit = tuple[str, str]


class Finding(NamedTuple):
    """One audit hit. `target` is the operand as written, the git subcommand,
    or the xargs'd reader name; `command` is the full original command."""

    kind: str
    target: str
    command: str


class AuditScope(NamedTuple):
    """Where a command runs: the repository `root` and the effective `cwd`.
    A `cwd` of None means a `cd` made it unknown."""

    root: str
    cwd: str | None


class _Word(NamedTuple):
    """A shell word with quoting removed. `has_expansion` marks a value the
    shell computes (`$x`, `$(..)`, backticks, `<(..)`); `nested` holds the
    commands inside those substitutions."""

    text: str
    has_expansion: bool = False
    nested: tuple[str, ...] = ()


class _Operator(NamedTuple):
    text: str


class _Redirect(NamedTuple):
    kind: str
    target: _Word


_Token = _Word | _Operator


def audit_commands(commands: list[str], root: str, cwd: str) -> list[Finding]:
    """Return the findings for `commands`, in command then segment order.

    Each command starts from `cwd`: the Bash tool resets cwd between calls.
    """
    scope = AuditScope(_normalize(root), _normalize(cwd))
    return [
        Finding(kind, target, command)
        for command in commands
        for kind, target in _audit(command, scope, 0)
    ]


def _audit(command: str, scope: AuditScope, depth: int) -> list[_Hit]:
    if depth > _MAX_DEPTH:
        return []
    hits: list[_Hit] = []
    for segment, piped in _segments(_lex(command)):
        segment_hits, scope = _audit_segment(segment, scope, depth, piped)
        hits.extend(segment_hits)
    return hits


def _audit_segment(
    segment: list[_Token], scope: AuditScope, depth: int, piped: bool
) -> tuple[list[_Hit], AuditScope]:
    words, redirects = _split_redirects(segment)
    command_words = _command_words(words)
    name = posixpath.basename(command_words[0].text) if command_words else ""
    args = command_words[1:]
    script = _shell_script(name, args)
    script_words = script[1] if script else []
    if name == _CMD_CD:
        scope = scope._replace(cwd=_next_cwd(args, scope.cwd))

    hits: list[_Hit] = []
    for word in words + [redirect.target for redirect in redirects]:
        if not any(word is consumed for consumed in script_words):
            hits.extend(_audit_nested(word, scope, depth))
    if script:
        hits.extend(_audit(script[0], scope, depth + 1))
    hits.extend(_classify_command(name, args, scope, piped))
    for redirect in redirects:
        hits.extend(_repo_hits(redirect.kind, [redirect.target], scope))
    return hits, scope


def _audit_nested(word: _Word, scope: AuditScope, depth: int) -> list[_Hit]:
    return [hit for inner in word.nested for hit in _audit(inner, scope, depth + 1)]


# --- lexer -----------------------------------------------------------------


def _lex(command: str) -> list[_Token]:
    return _Lexer(command).run()


class _Lexer:
    """Single-pass shell lexer: quotes, escapes, comments, substitutions,
    operators, and heredoc bodies (skipped, apart from the substitutions in an
    unquoted-delimiter body). An unterminated quote is ignored, so what
    follows it is still lexed (and audited) as ordinary shell."""

    def __init__(self, source: str) -> None:
        self._src = source
        self._pos = 0
        self._tokens: list[_Token] = []
        self._chars: list[str] = []
        self._in_word = False
        self._has_expansion = False
        self._nested: list[str] = []
        self._awaiting_delimiter = False
        self._strip_tabs = False
        self._quoted = False
        self._pending_heredocs: list[tuple[str, bool, bool]] = []

    def run(self) -> list[_Token]:
        while self._pos < len(self._src):
            self._step()
        self._flush()
        return self._tokens

    def _step(self) -> None:
        char = self._src[self._pos]
        if char in " \t":
            self._flush()
            self._pos += 1
        elif char == "\n":
            self._newline()
        elif char == "#" and not self._in_word:
            self._skip_comment()
        elif char == "\\":
            self._escape()
        elif char == "'":
            self._single_quoted()
        elif char == '"':
            self._double_quoted()
        elif char in "$`":
            self._expansion(char)
        elif char in "<>" and self._src.startswith("(", self._pos + 1):
            self._process_substitution()
        else:
            self._operator_or_literal(char)

    def _append(self, text: str, *, expands: bool = False) -> None:
        self._chars.append(text)
        self._in_word = True
        self._has_expansion = self._has_expansion or expands

    def _flush(self) -> None:
        if not self._in_word:
            return
        word = _Word("".join(self._chars), self._has_expansion, tuple(self._nested))
        if self._awaiting_delimiter:
            self._pending_heredocs.append((word.text, self._strip_tabs, self._quoted))
            self._awaiting_delimiter = False
        self._tokens.append(word)
        self._reset_word()

    def _reset_word(self) -> None:
        self._chars = []
        self._in_word = False
        self._has_expansion = False
        self._quoted = False
        self._nested = []

    def _newline(self) -> None:
        self._flush()
        self._awaiting_delimiter = False
        self._tokens.append(_Operator("\n"))
        self._pos += 1
        self._skip_heredoc_bodies()

    def _skip_heredoc_bodies(self) -> None:
        """Drop each pending heredoc body. Bash still runs `$(..)` and
        backticks in the body of an unquoted-delimiter heredoc, so those spans
        are emitted as a word of their own to be audited as nested commands."""
        src = self._src
        nested: list[str] = []
        for delimiter, strip_tabs, quoted in self._pending_heredocs:
            body: list[str] = []
            while self._pos < len(src):
                end = src.find("\n", self._pos)
                end = len(src) if end == -1 else end
                line = src[self._pos : end]
                self._pos = min(end + 1, len(src))
                if (line.lstrip("\t") if strip_tabs else line) == delimiter:
                    break
                body.append(line)
            if not quoted:
                nested.extend(_body_substitutions("\n".join(body)))
        self._pending_heredocs.clear()
        if nested:
            self._tokens.append(_Word("", True, tuple(nested)))
            self._tokens.append(_Operator("\n"))

    def _skip_comment(self) -> None:
        end = self._src.find("\n", self._pos)
        self._pos = len(self._src) if end == -1 else end

    def _escape(self) -> None:
        following = self._src[self._pos + 1 : self._pos + 2]
        self._quoted = True
        if following and following != "\n":
            self._append(following)
        self._pos += 2 if following else 1

    def _single_quoted(self) -> None:
        end = self._src.find("'", self._pos + 1)
        if end == -1:
            self._pos += 1
            return
        self._quoted = True
        self._append(self._src[self._pos + 1 : end])
        self._pos = end + 1

    def _double_quoted(self) -> None:
        src, index = self._src, self._pos + 1
        parts: list[str] = []
        nested: list[str] = []
        expands = False
        while index < len(src):
            char = src[index]
            if char == '"':
                self._quoted = True
                self._append("".join(parts), expands=expands)
                self._nested.extend(nested)
                self._pos = index + 1
                return
            if char == "\\" and src[index + 1 : index + 2] in _DOUBLE_QUOTE_ESCAPES:
                parts.append(src[index + 1])
                index += 2
            elif substitution := _command_substitution(src, index):
                inner, end = substitution
                parts.append(src[index:end])
                nested.append(inner)
                expands = True
                index = end
            else:
                parts.append(char)
                expands = expands or char == "$"
                index += 1
        self._pos += 1  # unterminated: ignore the quote

    def _expansion(self, char: str) -> None:
        src = self._src
        substitution = _command_substitution(src, self._pos)
        if substitution:
            inner, end = substitution
            self._append(src[self._pos : end], expands=True)
            self._nested.append(inner)
            self._pos = end
        elif src[self._pos + 1 : self._pos + 2] in ("'", '"'):
            self._quoted = True
            self._pos += 1  # `$'..'` and `$".."` quote like `'..'` and `".."`
        else:
            self._append(char, expands=True)
            self._pos += 1

    def _process_substitution(self) -> None:
        inner, end = _scan_parens(self._src, self._pos + 2)
        self._append("", expands=True)
        self._nested.append(inner)
        self._pos = end

    def _operator_or_literal(self, char: str) -> None:
        operator = next(
            (op for op in _OPERATORS if self._src.startswith(op, self._pos)), None
        )
        if operator is None:
            self._append(char)
            self._pos += 1
            return
        if operator not in _SEPARATORS and self._is_fd_prefix():
            self._reset_word()  # the `2` of `2>` names a descriptor
        else:
            self._flush()
        self._tokens.append(_Operator(operator))
        self._awaiting_delimiter = operator in _HEREDOC_OPS
        self._strip_tabs = operator == "<<-"
        self._pos += len(operator)

    def _is_fd_prefix(self) -> bool:
        text = "".join(self._chars)
        return (
            self._in_word
            and not self._has_expansion
            and text.isascii()
            and text.isdigit()
        )


def _command_substitution(src: str, pos: int) -> tuple[str, int] | None:
    """`(inner command, index after it)` when `$(` or a backtick starts at `pos`."""
    if src.startswith("$(", pos):
        return _scan_parens(src, pos + 2)
    if src.startswith("`", pos):
        return _scan_backtick(src, pos + 1)
    return None


def _body_substitutions(body: str) -> list[str]:
    """Inner commands of the `$(..)` and backtick spans in an unquoted heredoc
    body; a backslash-escaped `$` or backtick is literal."""
    inner: list[str] = []
    index = 0
    while index < len(body):
        if body[index] == "\\":
            index += 2
        elif substitution := _command_substitution(body, index):
            inner.append(substitution[0])
            index = substitution[1]
        else:
            index += 1
    return inner


def _scan_parens(src: str, start: int) -> tuple[str, int]:
    """Inner text of a parenthesised command that opens just before `start`."""
    depth, index = 1, start
    while index < len(src):
        char = src[index]
        if char == "\\":
            index += 2
            continue
        if char in "'\"":
            index = _skip_quoted(src, index)
            continue
        depth += (char == "(") - (char == ")")
        if depth == 0:
            return src[start:index], index + 1
        index += 1
    return src[start:], len(src)


def _scan_backtick(src: str, start: int) -> tuple[str, int]:
    index = start
    while index < len(src):
        if src[index] == "`":
            return src[start:index], index + 1
        index += 2 if src[index] == "\\" else 1
    return src[start:], len(src)


def _skip_quoted(src: str, start: int) -> int:
    quote, index = src[start], start + 1
    while index < len(src):
        if src[index] == quote:
            return index + 1
        index += 2 if src[index] == "\\" and quote == '"' else 1
    return len(src)


# --- segments and redirects ------------------------------------------------


def _segments(tokens: list[_Token]) -> list[tuple[list[_Token], bool]]:
    """`(tokens, piped)` per simple command. `piped` is True when a pipe feeds
    the command's stdin: a recursive reader with no path operand then reads
    that stream, not the working directory."""
    segments: list[tuple[list[_Token], bool]] = [([], False)]
    for token in tokens:
        if isinstance(token, _Operator) and token.text in _SEPARATORS:
            segments.append(([], token.text in _PIPES))
        else:
            segments[-1][0].append(token)
    return [(segment, piped) for segment, piped in segments if segment]


def _split_redirects(segment: list[_Token]) -> tuple[list[_Word], list[_Redirect]]:
    """Split a segment into its words and its file redirects. Fd duplications
    (`2>&1`, `>&2`), here-strings, and heredoc delimiters name no file."""
    words: list[_Word] = []
    redirects: list[_Redirect] = []
    index = 0
    while index < len(segment):
        token = segment[index]
        index += 1
        if isinstance(token, _Word):
            words.append(token)
            continue
        target = segment[index] if index < len(segment) else None
        if not isinstance(target, _Word):
            continue
        index += 1
        kind = _redirect_kind(token.text, target.text)
        if kind:
            redirects.append(_Redirect(kind, target))
    return words, redirects


def _redirect_kind(operator: str, target: str) -> str | None:
    if operator in _NO_FILE_OPS:
        return None
    if operator in _FD_DUP_OPS and _FD_TARGET.match(target):
        return None
    return KIND_READ if operator in _READ_REDIRECTS else KIND_WRITE


# --- command words ---------------------------------------------------------


def _command_words(words: list[_Word]) -> list[_Word]:
    """`words` from the command word on: leading `NAME=value` words, shell
    keywords, and wrapper commands (`env`, `timeout 5`, ...) are dropped."""
    rest = words
    while rest:
        head = rest[0].text
        wrapper = posixpath.basename(head)
        if _ASSIGNMENT.match(head) or head in _PREFIX_WORDS:
            rest = rest[1:]
        elif wrapper in _WRAPPERS:
            rest = _after_wrapper(wrapper, rest[1:])
        else:
            break
    return rest


def _after_wrapper(wrapper: str, words: list[_Word]) -> list[_Word]:
    value_flags = _WRAPPER_VALUE_FLAGS.get(wrapper, frozenset())
    index = 0
    while index < len(words) and words[index].text.startswith("-"):
        index += 2 if words[index].text in value_flags else 1
    if wrapper == _CMD_TIMEOUT:
        index += 1  # the duration
    return words[index:]


def _shell_script(name: str, args: list[_Word]) -> tuple[str, list[_Word]] | None:
    """The script text `eval`, `bash -c`, or `sh -c` runs, with the words that
    hold it, or None."""
    if name == _CMD_EVAL and args:
        return " ".join(arg.text for arg in args), args
    if name in _SHELLS:
        for index, arg in enumerate(args[:-1]):
            if _is_command_flag(arg.text):
                return args[index + 1].text, [args[index + 1]]
    return None


def _is_command_flag(flag: str) -> bool:
    """A short-flag cluster containing `c` (`-c`, `-lc`), not a long flag."""
    return flag.startswith("-") and not flag.startswith("--") and "c" in flag[1:]


def _next_cwd(args: list[_Word], cwd: str | None) -> str | None:
    """Lexical cwd after `cd`; None when the target cannot be resolved."""
    operands = _operands(args)
    if not operands or operands[0].has_expansion:
        return None
    return _resolve_operand(operands[0].text, cwd)


def _classify_command(
    name: str, args: list[_Word], scope: AuditScope, piped: bool
) -> list[_Hit]:
    if name == _CMD_GIT:
        return _classify_git(args)
    if name == _CMD_XARGS:
        reader = _first_positional(args, _XARGS_VALUE_FLAGS)
        reader_name = posixpath.basename(reader.text) if reader else ""
        return [(KIND_XARGS, reader_name)] if reader_name in READERS else []
    if name in WRITERS:
        return _repo_hits(KIND_WRITE, _operands(args), scope)
    if name == _CMD_DD:
        return _repo_hits(KIND_READ, _dd_inputs(args), scope)
    if name in READERS:
        kind = KIND_WRITE if name == _CMD_SED and _is_in_place(args) else KIND_READ
        return _repo_hits(kind, _reader_operands(name, args, piped), scope)
    return []


def _dd_inputs(args: list[_Word]) -> list[_Word]:
    """The `if=<path>` operands of `dd`, as plain path words."""
    return [
        _Word(arg.text[len(_DD_INPUT_PREFIX) :], arg.has_expansion)
        for arg in args
        if arg.text.startswith(_DD_INPUT_PREFIX)
    ]


def _classify_git(args: list[_Word]) -> list[_Hit]:
    if _defines_alias(args):
        return [(KIND_GIT, _GIT_ALIAS_TARGET)]
    subcommand = _first_positional(args, _GIT_VALUE_FLAGS)
    if not subcommand or not (
        subcommand.text in GIT_READ or subcommand.text in GIT_WRITE
    ):
        return []
    rest = args[_index_of(args, subcommand) + 1 :]
    if _is_read_only_git_form(subcommand.text, rest):
        return []
    return [(KIND_GIT, subcommand.text)]


def _index_of(args: list[_Word], word: _Word) -> int:
    """Position of `word` in `args` by identity, so an equal earlier word
    (a flag value) is never mistaken for it."""
    return next(index for index, arg in enumerate(args) if arg is word)


def _is_read_only_git_form(subcommand: str, rest: list[_Word]) -> bool:
    """True for a listing or query form of a write-capable git verb.

    `branch`/`tag`/`remote`/`worktree`: no operands, or listing flags only,
    or a listing flag or keyword (`remote show`, `worktree list`) with its
    patterns. `config`: a read flag (`--get`, `--list`, ...) with scope flags
    only. `symbolic-ref`: query flags and at most one ref. Anything else on
    these verbs writes.
    """
    flags = [word.text for word in rest if word.text.startswith("-")]
    operands = [word.text for word in rest if not word.text.startswith("-")]
    if subcommand in _GIT_LISTING_VERBS:
        if any(flag not in _GIT_READ_ONLY_FLAGS for flag in flags):
            return False
        listing_flag = any(flag in _GIT_LISTING_ONLY_FLAGS for flag in flags)
        keyword = _GIT_LISTING_KEYWORD_BY_VERB.get(subcommand)
        listing_word = bool(operands) and operands[0] == keyword
        return not operands or listing_flag or listing_word
    if subcommand == "config":
        return any(flag in _GIT_CONFIG_READ_FLAGS for flag in flags) and all(
            flag in _GIT_CONFIG_READ_FLAGS | _GIT_CONFIG_SCOPE_FLAGS for flag in flags
        )
    if subcommand == "symbolic-ref":
        return len(operands) <= 1 and all(
            flag in _GIT_SYMBOLIC_REF_FLAGS for flag in flags
        )
    return False


def _defines_alias(args: list[_Word]) -> bool:
    """`-c alias.x=...` or `--config-env`: the subcommand name proves nothing."""
    return any(arg.text.startswith("--config-env") for arg in args) or any(
        flag.text == "-c" and value.text.lower().startswith("alias.")
        for flag, value in pairwise(args)
    )


def _first_positional(args: list[_Word], value_flags: frozenset[str]) -> _Word | None:
    """First non-flag word, skipping the values of `value_flags`."""
    skip_value = False
    for arg in args:
        if skip_value:
            skip_value = False
        elif arg.text in value_flags:
            skip_value = True
        elif not arg.text.startswith("-"):
            return arg
    return None


def _is_in_place(args: list[_Word]) -> bool:
    return any(arg.text.startswith(("-i", "--in-place")) for arg in args)


def _operands(args: list[_Word]) -> list[_Word]:
    """Non-flag words; a lone `-` counts as an operand, `--` ends the flags."""
    operands: list[_Word] = []
    flags_ended = False
    for arg in args:
        if arg.text == _END_OF_FLAGS and not flags_ended:
            flags_ended = True
        elif flags_ended or arg.text == _STDIN_OPERAND or not arg.text.startswith("-"):
            operands.append(arg)
    return operands


def _reader_operands(name: str, args: list[_Word], piped: bool) -> list[_Word]:
    """Candidate path operands of a reader, after flag values and the leading
    pattern or script are removed. A recursive search that is not fed by a
    pipe and names no path searches the working directory: an implicit `.`."""
    value_flags = _VALUE_FLAGS.get(name, frozenset())
    pattern_flags = _PATTERN_FLAGS.get(name, frozenset())
    operands: list[_Word] = []
    has_pattern_flag = False
    skip_values = 0
    flags_ended = False
    for arg in args:
        text = arg.text
        if skip_values:
            skip_values -= 1
        elif flags_ended or text == _STDIN_OPERAND or not text.startswith("-"):
            operands.append(arg)
        elif text == _END_OF_FLAGS:
            flags_ended = True
        else:
            flag = text.partition("=")[0] if text.startswith("--") else text[:2]
            has_pattern_flag = has_pattern_flag or flag in pattern_flags
            skip_values = _values_to_skip(text, value_flags)
    if name in _PATTERN_FLAGS and not has_pattern_flag:
        operands = operands[1:]
    if not operands and not piped and _searches_cwd_by_default(name, args):
        return [_Word(_IMPLICIT_OPERAND)]
    return operands


def _searches_cwd_by_default(name: str, args: list[_Word]) -> bool:
    """`rg`, and `grep` with a recursive flag, search `.` when given no path."""
    return name == _CMD_RG or (name == _CMD_GREP and _is_recursive_grep(args))


def _is_recursive_grep(args: list[_Word]) -> bool:
    """`-r`, `-R`, `--recursive`, `-d recurse`, or a short cluster holding
    `r`/`R` ahead of any value-taking letter (`-rn`, `-nR`)."""
    texts = [arg.text for arg in args]
    for index, text in enumerate(texts):
        if text == _END_OF_FLAGS:
            return False
        if text in _GREP_RECURSIVE_FLAGS:
            return True
        if text in _GREP_DIRECTORIES_FLAGS and texts[index + 1 : index + 2] == [
            _GREP_RECURSE
        ]:
            return True
        if (
            text.startswith("-")
            and not text.startswith("--")
            and _short_cluster_recurses(text)
        ):
            return True
    return False


def _short_cluster_recurses(cluster: str) -> bool:
    for letter in cluster[1:]:
        if letter in "rR":
            return True
        if letter in _GREP_VALUE_LETTERS:
            return False  # the rest of the cluster is that flag's value
    return False


def _values_to_skip(flag: str, value_flags: frozenset[str]) -> int:
    """Tokens after `flag` it consumes. Attached values (`-A3`, `--max=1`)
    are not in `value_flags` and consume nothing."""
    if flag not in value_flags:
        return 0
    return 2 if flag in _JQ_BINDING_FLAGS else 1


# --- paths -----------------------------------------------------------------


def _repo_hits(kind: str, operands: list[_Word], scope: AuditScope) -> list[_Hit]:
    return [
        (kind, operand.text)
        for operand in operands
        if _is_candidate(kind, operand) and _is_repo_path(operand.text, scope)
    ]


def _is_candidate(kind: str, operand: _Word) -> bool:
    """False for operands that are never findings: shell-computed values,
    empty words, stdin, and `.feature` reads."""
    text = operand.text
    if operand.has_expansion or not text or text == _STDIN_OPERAND:
        return False
    return not (kind == KIND_READ and text.endswith(FEATURE_SUFFIX))


def _normalize(path: str) -> str:
    normalized = posixpath.normpath(path)
    # POSIX keeps exactly two leading slashes; Linux and macOS read `//` as `/`.
    return normalized[1:] if normalized.startswith("//") else normalized


def _resolve_operand(operand: str, cwd: str | None) -> str | None:
    """Absolute lexical path of `operand`, or None when it cannot be resolved
    (home, `-`, `~-`, or a relative path with an unknown cwd)."""
    if operand.startswith("~+") and cwd is not None:
        return _normalize(posixpath.join(cwd, operand[2:].lstrip("/")))
    if operand.startswith("~") or operand == _STDIN_OPERAND:
        return None
    if operand == _PROC_SELF_CWD or operand.startswith(_PROC_SELF_CWD + "/"):
        if cwd is None:
            return None
        operand = cwd + operand[len(_PROC_SELF_CWD) :]
    if posixpath.isabs(operand):
        return _normalize(operand)
    if cwd is None:
        return None
    return _normalize(posixpath.join(cwd, operand))


def _is_inside(path: str, base: str) -> bool:
    return path == base or path.startswith(base.rstrip("/") + "/")


def _is_repo_path(operand: str, scope: AuditScope) -> bool:
    """True when `operand` is, or as a glob may be, inside the repository."""
    glob = _GLOB_CHARS.search(operand)
    literal = operand if glob is None else operand[: glob.start()]
    resolved = _resolve_operand(literal, scope.cwd)
    if resolved is None:
        # Unresolvable (home tilde, `-`, unknown cwd): possibly inside the repo.
        return True
    if _is_inside(resolved, scope.root):
        return True
    if glob is None:
        return False
    if literal.endswith("/") or not literal:
        return _is_inside(scope.root, resolved)  # the glob can enter root
    return scope.root.startswith(resolved)  # the glob completes `/re` to `/repo`
