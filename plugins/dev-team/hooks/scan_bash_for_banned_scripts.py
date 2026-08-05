#!/usr/bin/env python3
"""scan_bash_for_banned_scripts.py — real-time PreToolUse denial of new
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
a guarantee it can't back. `scan_banned_scripts.py` (PostToolUse, `*`
matcher) is the required backstop: it inspects the real working tree after
every tool call, catching anything this scan misses regardless of which
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

_REDIRECT_RE = re.compile(r">>?\s*([^\s;|&<>]+)")


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


def _parse_destination_args(args: list[str]) -> tuple[str | None, list[str]]:
    """Tokenize `cp`/`mv` arguments (after the program name) into a GNU
    target-directory value (`-t DIR` / `--target-directory=DIR` /
    `--target-directory DIR`) and the remaining positional arguments.

    Returns `(target_dir, positionals)`. `target_dir` is `None` when no
    target-directory form was used, and the caller falls back to treating
    the last positional as the destination (#1875).
    """
    target_dir: str | None = None
    positionals: list[str] = []
    i = 0
    n = len(args)
    while i < n:
        arg = args[i]
        if arg.startswith("--target-directory="):
            target_dir = arg.split("=", 1)[1]
            i += 1
            continue
        if arg == "--target-directory" and i + 1 < n:
            target_dir = args[i + 1]
            i += 2
            continue
        # A single-dash cluster ending in `t` (`-t`, `-rt`, `-at`, `-vt`, ...)
        # is GNU coreutils' clustered-short-option form of `-t DIR` — the
        # unclustered `-t` alone was the only form recognized before, so
        # `cp -rt DIR src.sh` fell through to the (wrong) last-positional
        # heuristic below and evaded detection.
        if (
            arg.startswith("-")
            and not arg.startswith("--")
            and len(arg) > 1
            and arg.endswith("t")
            and i + 1 < n
        ):
            target_dir = args[i + 1]
            i += 2
            continue
        if arg.startswith("-") and arg != "-":
            i += 1
            continue
        positionals.append(arg)
        i += 1
    return target_dir, positionals


def _copy_move_tee_targets(command: str) -> list[str]:
    """Best-effort tokenization to catch `cp`/`mv`/`tee` destinations.

    Splits on shell command separators first so each simple command
    tokenizes on its own — a single `shlex.split()` over a compound command
    (`a && b`) would otherwise misattribute tokens across commands. Also
    splits on a bare newline/`\r` and a single `&` (background job): a
    multi-line command or `a & b` previously collapsed into one `shlex`
    call, so `positionals[-1]` in the cp/mv branch below read the LAST
    command's last token instead of the actual cp/mv destination — a
    real bypass of the destination heuristic, not just a style gap.
    Malformed quoting is skipped, never crashed on: a scan error must fail
    open, not block a legitimate command it couldn't parse.
    """
    targets: list[str] = []
    for segment in re.split(r"&&|\|\||[;|&\n\r]", command):
        segment = segment.strip()
        if not segment:
            continue
        try:
            tokens = shlex.split(segment)
        except ValueError:
            continue
        if not tokens:
            continue
        prog = Path(tokens[0]).name
        if prog == "tee":
            # tee writes to every named file, not just the last.
            args = [t for t in tokens[1:] if not t.startswith("-")]
            targets.extend(a for a in args if _has_banned_extension(a))
        elif prog in ("cp", "mv"):
            target_dir, positionals = _parse_destination_args(tokens[1:])
            if target_dir is not None:
                # GNU target-directory form (#1878): every remaining
                # positional is a SOURCE being copied/moved INTO
                # target_dir — the effective write target is
                # target_dir/basename(source) for each one.
                for source in positionals:
                    dest = f"{target_dir.rstrip('/')}/{Path(source).name}"
                    if _has_banned_extension(dest):
                        targets.append(dest)
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
