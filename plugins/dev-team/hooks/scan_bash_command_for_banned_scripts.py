#!/usr/bin/env python3
"""scan_bash_command_for_banned_scripts.py — real-time PreToolUse denial of new
shell-script writes under plugins/dev-team/ (#1755).

This repo's own CLAUDE.md states the rule ("every shipped
plugins/dev-team/ script is Python 3.10+ stdlib-only", ADR 0014/0015) and CI
has a `check-python-only` gate, but neither stops a `.sh`/`.bash`/`.bat`/
`.cmd`/`.ps1` file from being written *during* a session — the violation was
only caught later, in code review or CI. This hook closes that gap at the
point of the `Bash` tool call itself, before the write happens.

Heuristic, not exhaustive: it regex/token-scans the command string for
redirect (`>`, `>>`), `cp`, `mv`, and `tee` write targets. A sufficiently
obfuscated command (base64-decoded write, a wrapper script, `eval`) can
evade it — this hook's own scan says so, deliberately, rather than implying
a guarantee it can't back. `scan_worktree_for_banned_scripts.py` (PostToolUse,
`*` matcher) is the required backstop: it inspects the real working tree
after every tool call, catching anything this scan misses regardless of which
tool wrote it.

Contract (docs/python-hook-contract.md):
    Input : PreToolUse JSON on stdin with tool_input.command (Bash matcher)
    Output: exit 0 = allow; exit 2 = block (message on stdout AND stderr)

Stdlib-only. See ADR 0014/0015.
"""

from __future__ import annotations

import re
import shlex
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_LIB_DIR = _SCRIPT_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from artifact_paths import project_root
from banned_scripts_policy import (
    ALLOWED_RELATIVE_PATHS,
    BANNED_EXTENSIONS,
    SCOPED_PREFIX,
    looks_like_monorepo_checkout,
)
from stdin_json import read_stdin_json

# `>|` is tolerated between the operator and its target (bash's
# force-overwrite/noclobber-override redirect) — without it, `|` sits
# outside the capture class and the whole match silently fails, letting a
# `>|`-redirected banned write escape `_redirect_targets` entirely.
_REDIRECT_RE = re.compile(r">>?\|?\s*([^\s;|&<>]+)")

# (#1904 item 12) Shell metacharacters always tokenized on their own,
# regardless of adjacent whitespace, by `_tokenize_command`'s
# `punctuation_chars` lexer. `\n` is included so a bare newline between two
# commands is a real segment boundary rather than being swallowed as
# ordinary whitespace (the default `shlex` behavior, which would silently
# merge two unrelated commands' tokens into one stream).
#
# `|&` (bash shorthand for `2>&1 |`) and `;&` (a case-statement fallthrough
# terminator) are real command separators too — both group into a single
# lexer token, same as `&&`/`||`, and omitting them left a command like
# `true |& cp evil.sh dest.sh` as one un-split segment whose `prog` resolved
# to `true`, never reaching the cp/mv destination check at all.
_PUNCTUATION_CHARS = "();<>|&\n"
_COMMAND_SEPARATORS = frozenset({"&&", "||", ";", "&", "|", "|&", ";&", "\n"})
_OPERATOR_CHARS = frozenset("();<>|&")

# (#1904 item 13) GNU's attached-value form for a short-option cluster
# ending in `t` (`-tDIR`, `-rtDIR`) — the value is glued directly onto the
# cluster with no space, distinct from the detached `-t DIR` / `-rt DIR`
# form handled separately in `_parse_destination_args`.
_ATTACHED_TARGET_DIR_RE = re.compile(r"^-[^-]*t(?P<value>.+)$")
_TARGET_DIRECTORY_LONG_OPTION = "--target-directory"


def _has_banned_extension(path_str: str) -> bool:
    return path_str.lower().endswith(BANNED_EXTENSIONS)


def _strip_quotes(token: str) -> str:
    """Strip one matching pair of leading/trailing quote characters.

    The redirect regex's capture group has no notion of shell quoting, so
    `> "evil.sh"` captures the target WITH its surrounding quotes — which
    then fails `.endswith(".sh")` (#1864 sub-claim 3). This normalizes the
    captured text before the extension check, nothing more.
    """
    if len(token) >= 2 and token[0] == token[-1] and token[0] in ("'", '"'):
        return token[1:-1]
    return token


def _redirect_targets(command: str) -> list[str]:
    targets = []
    for match in _REDIRECT_RE.finditer(command):
        target = _strip_quotes(match.group(1))
        if _has_banned_extension(target):
            targets.append(target)
    return targets


def _match_long_target_directory(args: list[str], i: int, n: int) -> tuple[int, str | None]:
    """`--target-directory=DIR` or the detached `--target-directory DIR`.

    Returns `(tokens_consumed, target_dir)` — `(0, None)` on no match, the
    contract every matcher in `_TARGET_DIR_MATCHERS` shares.
    """
    arg = args[i]
    if arg.startswith("--target-directory="):
        return 1, arg.split("=", 1)[1]
    if arg == "--target-directory" and i + 1 < n:
        return 2, args[i + 1]
    return 0, None


def _match_abbreviated_long_option(args: list[str], i: int, n: int) -> tuple[int, str | None]:
    """An unambiguous abbreviation of `--target-directory=` (e.g.
    `--target-dir=DIR`) — cp/mv define no other `--target-*` long option,
    so any prefix is unambiguous (mirrors GNU getopt_long's own
    abbreviation rule). Checked before the `=` split so a boundary must
    actually exist (#1904 item 13)."""
    del n
    arg = args[i]
    if arg.startswith("--") and "=" in arg:
        flag, _, value = arg.partition("=")
        if len(flag) > 2 and _TARGET_DIRECTORY_LONG_OPTION.startswith(flag):
            return 1, value
    return 0, None


def _match_attached_short_option(args: list[str], i: int, n: int) -> tuple[int, str | None]:
    """GNU's attached-value form: the value is glued directly onto a
    short-option cluster ending in `t`, with no space (`-tDIR`, `-rtDIR`) —
    distinct from the detached `-t DIR` form (#1904 item 13)."""
    del n
    arg = args[i]
    if arg.startswith("-") and not arg.startswith("--"):
        attached = _ATTACHED_TARGET_DIR_RE.match(arg)
        if attached:
            return 1, attached.group("value")
    return 0, None


def _match_clustered_short_option(args: list[str], i: int, n: int) -> tuple[int, str | None]:
    """A single-dash cluster ending in `t` (`-t`, `-rt`, `-at`, `-vt`, ...)
    is GNU coreutils' clustered-short-option form of `-t DIR` — the
    unclustered `-t` alone was the only form recognized before, so
    `cp -rt DIR src.sh` fell through to the (wrong) last-positional
    heuristic and evaded detection."""
    arg = args[i]
    if (
        arg.startswith("-")
        and not arg.startswith("--")
        and len(arg) > 1
        and arg.endswith("t")
        and i + 1 < n
    ):
        return 2, args[i + 1]
    return 0, None


_TARGET_DIR_MATCHERS = (
    _match_long_target_directory,
    _match_abbreviated_long_option,
    _match_attached_short_option,
    _match_clustered_short_option,
)


def _parse_destination_args(args: list[str]) -> tuple[str | None, list[str]]:
    """Tokenize `cp`/`mv` arguments (after the program name) into a GNU
    target-directory value (`-t DIR` / `--target-directory=DIR` /
    `--target-directory DIR`, plus the attached/abbreviated/clustered
    variants in `_TARGET_DIR_MATCHERS`) and the remaining positional
    arguments.

    Returns `(target_dir, positionals)`. `target_dir` is `None` when no
    target-directory form was used, and the caller falls back to treating
    the last positional as the destination (#1875). A dispatch loop over
    `_TARGET_DIR_MATCHERS`, in order — first match wins, mirroring the
    original if/elif precedence.
    """
    target_dir: str | None = None
    positionals: list[str] = []
    i = 0
    n = len(args)
    while i < n:
        arg = args[i]
        matched = False
        for matcher in _TARGET_DIR_MATCHERS:
            consumed, value = matcher(args, i, n)
            if consumed:
                target_dir = value
                i += consumed
                matched = True
                break
        if matched:
            continue
        if arg.startswith("-") and arg != "-":
            i += 1
            continue
        positionals.append(arg)
        i += 1
    return target_dir, positionals


def _tokenize_command(command: str) -> list[str]:
    """Tokenize the whole command once, quote-aware, with shell
    metacharacters always returned as their own tokens regardless of
    adjacent whitespace (#1904 item 12b). This is what makes a quoted
    separator or redirect character (`"a&b.sh"`, `"a>b.sh"`) survive as
    literal content of the word it belongs to, instead of desyncing a plain
    string split/regex over the raw command text — the previous approach's
    `re.split` had no notion of quoting, so a separator character inside
    quotes silently broke the word apart mid-token.

    Raises `ValueError` on malformed quoting; callers must fail open (skip,
    never crash) on that, matching the rest of this hook's contract.
    """
    lexer = shlex.shlex(command, posix=True, punctuation_chars=_PUNCTUATION_CHARS)
    lexer.whitespace_split = True
    lexer.whitespace = " \t\r"
    return list(lexer)


def _segment_simple_commands(tokens: list[str]) -> list[list[str]]:
    """Split a flat token stream into one list per simple command, breaking
    at command-separator tokens (`&&`, `||`, `;`, `&`, `|`, or a bare
    newline) — the tokenized replacement for the old raw-string
    `re.split(r"&&|\\|\\||[;|&\\n\\r]", command)` (#1904 item 12b)."""
    segments: list[list[str]] = []
    current: list[str] = []
    for tok in tokens:
        if tok in _COMMAND_SEPARATORS:
            if current:
                segments.append(current)
            current = []
            continue
        current.append(tok)
    if current:
        segments.append(current)
    return segments


def _is_operator_token(tok: str) -> bool:
    """True when every character in `tok` is a shell metacharacter — the
    heuristic signature of an UNQUOTED occurrence.

    KNOWN LIMITATION: this is imperfect in posix `shlex` mode. A wholly
    quoted metacharacter sequence normalizes to the IDENTICAL token text as
    the real unquoted operator — `shlex` strips quotes before this
    function ever sees the token, so `tee ";" plugins/dev-team/hooks/
    evil.sh` produces the same `";"` token as an actual unquoted `;`
    separator, and `_segment_simple_commands` splits `tee` from its own
    (quoted, literal) destination argument. This lets that destination
    escape detection. A correct fix needs per-token quotedness tracked
    from the lexer itself (subclassing `shlex.shlex.read_token` to record
    whether a quote character was consumed) rather than inferred from the
    token's content after the fact — a larger tokenizer rework than this
    fix; see `test_quoted_semicolon_argument_known_limitation_evades_scan`
    in the test suite for the exact repro, tracked as a follow-up rather
    than silently left unaddressed."""
    return bool(tok) and all(c in _OPERATOR_CHARS for c in tok)


def _strip_redirects(tokens: list[str]) -> list[str]:
    """Drop every unquoted redirect/operator token, the operand
    immediately following one, and a bare file-descriptor digit
    immediately preceding one (`2>err.log`, `2>&1`), from a simple
    command's token list (#1904 item 12a) — a trailing shell redirect
    (`... 2>/dev/null`, `... > /dev/null`) must never be mistaken for a
    `cp`/`mv` positional destination argument.

    Any operator token CONTAINING `>` consumes its following operand, not
    just the two literal forms `>`/`>>` — `shlex`'s `punctuation_chars`
    lexer groups a run of adjacent metacharacters into one multi-character
    token, so bash's `&>`, `>&`, `>|`, and fd-duplication forms like
    `2>&1` all arrive as a single `>`-containing token distinct from a
    bare `>`/`>>`. Treating only the two literal forms as redirects left
    every one of those evading this heuristic entirely, since their
    trailing operand (e.g. `/dev/null`, a bare fd number) would survive
    into the positional-argument list and get mistaken for the real
    destination.
    """
    cleaned: list[str] = []
    i = 0
    n = len(tokens)
    while i < n:
        tok = tokens[i]
        if (
            tok.isdigit()
            and i + 1 < n
            and _is_operator_token(tokens[i + 1])
            and ">" in tokens[i + 1]
        ):
            i += 3 if i + 2 < n else 2
            continue
        if _is_operator_token(tok) and ">" in tok:
            i += 2 if i + 1 < n else 1
            continue
        if _is_operator_token(tok):
            i += 1
            continue
        cleaned.append(tok)
        i += 1
    return cleaned


def _target_dir_destinations(target_dir: str, positionals: list[str]) -> list[str]:
    """Expand a GNU target-directory `cp`/`mv` invocation (#1878) into its
    effective per-source write targets: `target_dir/basename(source)` for
    every remaining positional, filtered to banned extensions."""
    destinations: list[str] = []
    for source in positionals:
        dest = f"{target_dir.rstrip('/')}/{Path(source).name}"
        if _has_banned_extension(dest):
            destinations.append(dest)
    return destinations


def _copy_move_tee_targets(command: str) -> list[str]:
    """Best-effort tokenization to catch `cp`/`mv`/`tee` destinations.

    Tokenizes the whole command once via `_tokenize_command` and segments
    on the resulting command-separator tokens (#1904 item 12), rather than
    regex-splitting the raw command string first. Each segment then has its
    trailing shell redirect stripped via `_strip_redirects` before the
    last-positional-is-the-destination heuristic runs. Malformed quoting is
    skipped, never crashed on: a scan error must fail open, not block a
    legitimate command it couldn't parse.
    """
    targets: list[str] = []
    try:
        tokens = _tokenize_command(command)
    except ValueError:
        return targets
    for segment in _segment_simple_commands(tokens):
        segment = _strip_redirects(segment)
        if not segment:
            continue
        prog = Path(segment[0]).name
        if prog == "tee":
            # tee writes to every named file, not just the last.
            args = [t for t in segment[1:] if not t.startswith("-")]
            targets.extend(a for a in args if _has_banned_extension(a))
        elif prog in ("cp", "mv"):
            target_dir, positionals = _parse_destination_args(segment[1:])
            if target_dir is not None:
                # GNU target-directory form (#1878): every remaining
                # positional is a SOURCE being copied/moved INTO
                # target_dir.
                targets.extend(_target_dir_destinations(target_dir, positionals))
            elif positionals and _has_banned_extension(positionals[-1]):
                # Fixed #1875 heuristic: the destination is the actual last
                # positional argument — never an earlier source, even one
                # with a banned extension (e.g. `mv evil.sh good.py`, the
                # correct remediation, must not be flagged).
                targets.append(positionals[-1])
    return targets


def _scoped_relative_path(target: str, cwd: Path, root: Path) -> str | None:
    """Resolve `target` (as written in the command) against `cwd`, then
    return its path relative to `root` in POSIX form — or ``None`` when it
    resolves outside `root` entirely."""
    candidate = Path(target)
    resolved = candidate if candidate.is_absolute() else (cwd / candidate)
    try:
        rel = resolved.resolve().relative_to(root.resolve())
    except ValueError:
        return None
    return rel.as_posix()


def find_banned_write(command: str, cwd: Path, root: Path) -> str | None:
    """Return the first plugins/dev-team/-scoped banned-extension write
    target in `command` (relative to `root`), or ``None``. Skips the two
    documented bootstrap-shim carve-outs."""
    for target in [*_redirect_targets(command), *_copy_move_tee_targets(command)]:
        rel = _scoped_relative_path(target, cwd, root)
        if rel is None or not rel.startswith(SCOPED_PREFIX):
            continue
        if rel in ALLOWED_RELATIVE_PATHS:
            continue
        return rel
    return None


def main() -> int:
    payload = read_stdin_json() or {}

    tool_input = payload.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str) or not command.strip():
        return 0

    cwd = Path(payload.get("cwd") or ".")

    # (#1861) Cheap, non-git early exit for any checkout where this
    # monorepo's own plugins/dev-team/ tree doesn't exist — e.g. every
    # downstream install of the plugin. Checked via a plain filesystem walk
    # BEFORE project_root() (which itself shells out to git), not after.
    if not looks_like_monorepo_checkout(cwd):
        return 0

    root = project_root(cwd)
    hit = find_banned_write(command, cwd, root)
    if hit is None:
        return 0

    message = (
        f"[BLOCK] {hit} is a shell-script write under plugins/dev-team/. "
        "Every shipped script there must be Python 3.10+ stdlib-only "
        "(ADR 0014/0015; repo CLAUDE.md § Script authoring). Write a "
        ".py module instead, or confirm this is genuinely one of the two "
        "documented bootstrap-shim exceptions (plugins/dev-team/install.sh, "
        "plugins/dev-team/hooks/py.sh)."
    )
    sys.stdout.write(message + "\n")
    sys.stderr.write(message + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
